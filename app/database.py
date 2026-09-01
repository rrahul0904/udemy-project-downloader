from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .learning_library import MEDIA_EXTENSIONS, TRANSCRIPT_EXTENSIONS, build_library, load_transcript

SCHEMA_VERSION = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _logical_transcript_key(path: str) -> str:
    p = Path(path)
    name = p.name
    for suffix in sorted(TRANSCRIPT_EXTENSIONS, key=len, reverse=True):
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
            break
    name = re.sub(r"\.[A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?$", "", name)
    return (p.parent / name).as_posix().casefold()


class CourseStore:
    """Durable local Course Intelligence store backed by SQLite + FTS5."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def migrate(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS courses (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    directory TEXT NOT NULL UNIQUE,
                    source_platform TEXT,
                    source_url TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sections (
                    id TEXT PRIMARY KEY,
                    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    position INTEGER,
                    UNIQUE(course_id, title)
                );
                CREATE TABLE IF NOT EXISTS lessons (
                    id TEXT PRIMARY KEY,
                    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                    section_id TEXT REFERENCES sections(id) ON DELETE SET NULL,
                    title TEXT NOT NULL,
                    position INTEGER,
                    source_platform TEXT,
                    source_url TEXT,
                    source_id TEXT,
                    media_path TEXT,
                    transcript_path TEXT NOT NULL UNIQUE,
                    transcript_format TEXT NOT NULL,
                    language TEXT,
                    duration REAL,
                    uploader TEXT,
                    thumbnail TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS transcripts (
                    id TEXT PRIMARY KEY,
                    lesson_id TEXT NOT NULL UNIQUE REFERENCES lessons(id) ON DELETE CASCADE,
                    path TEXT NOT NULL UNIQUE,
                    format TEXT NOT NULL,
                    language TEXT,
                    content_hash TEXT NOT NULL,
                    word_count INTEGER NOT NULL,
                    has_timestamps INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS transcript_segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transcript_id TEXT NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
                    lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
                    segment_index INTEGER NOT NULL,
                    start_ms INTEGER,
                    end_ms INTEGER,
                    text TEXT NOT NULL,
                    UNIQUE(transcript_id, segment_index)
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS transcript_fts USING fts5(
                    text,
                    transcript_id UNINDEXED,
                    lesson_id UNINDEXED,
                    start_ms UNINDEXED,
                    end_ms UNINDEXED,
                    tokenize='unicode61'
                );
                CREATE TABLE IF NOT EXISTS notes (
                    lesson_id TEXT PRIMARY KEY REFERENCES lessons(id) ON DELETE CASCADE,
                    body TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS bookmarks (
                    id TEXT PRIMARY KEY,
                    lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
                    segment_index INTEGER NOT NULL,
                    start_ms INTEGER,
                    end_ms INTEGER,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(lesson_id, segment_index)
                );
                CREATE TABLE IF NOT EXISTS study_progress (
                    lesson_id TEXT PRIMARY KEY REFERENCES lessons(id) ON DELETE CASCADE,
                    last_position_ms INTEGER,
                    completed INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                """
            )
            current = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] or 0
            if current < 2:
                self._migrate_v2(conn)
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, _now()),
            )

    def _migrate_v2(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(transcripts)")}
        if "source_kind" not in columns:
            conn.executescript(
                """
                CREATE TABLE transcripts_v2 (
                    id TEXT PRIMARY KEY,
                    lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
                    path TEXT NOT NULL UNIQUE,
                    format TEXT NOT NULL,
                    language TEXT NOT NULL DEFAULT 'und',
                    source_kind TEXT NOT NULL DEFAULT 'imported',
                    provenance_json TEXT NOT NULL DEFAULT '{}',
                    version INTEGER NOT NULL DEFAULT 1,
                    content_hash TEXT NOT NULL,
                    word_count INTEGER NOT NULL,
                    has_timestamps INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE transcript_segments_v2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transcript_id TEXT NOT NULL REFERENCES transcripts_v2(id) ON DELETE CASCADE,
                    lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
                    segment_index INTEGER NOT NULL,
                    start_ms INTEGER,
                    end_ms INTEGER,
                    text TEXT NOT NULL,
                    UNIQUE(transcript_id, segment_index)
                );
                INSERT INTO transcripts_v2(
                    id,lesson_id,path,format,language,source_kind,provenance_json,version,
                    content_hash,word_count,has_timestamps,created_at,updated_at
                )
                SELECT id,lesson_id,path,format,COALESCE(NULLIF(language,''),'und'),'imported','{}',1,
                       content_hash,word_count,has_timestamps,updated_at,updated_at
                FROM transcripts;
                INSERT INTO transcript_segments_v2(
                    id,transcript_id,lesson_id,segment_index,start_ms,end_ms,text
                )
                SELECT id,transcript_id,lesson_id,segment_index,start_ms,end_ms,text
                FROM transcript_segments;
                DROP TABLE transcript_segments;
                DROP TABLE transcripts;
                ALTER TABLE transcripts_v2 RENAME TO transcripts;
                ALTER TABLE transcript_segments_v2 RENAME TO transcript_segments;
                """
            )
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS attachments (
                id TEXT PRIMARY KEY,
                course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                lesson_id TEXT REFERENCES lessons(id) ON DELETE SET NULL,
                filename TEXT NOT NULL,
                relative_path TEXT NOT NULL UNIQUE,
                mime_type TEXT,
                size INTEGER NOT NULL,
                source_url TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sections_course_position
                ON sections(course_id, position);
            CREATE INDEX IF NOT EXISTS idx_lessons_section_position
                ON lessons(section_id, position);
            CREATE INDEX IF NOT EXISTS idx_transcripts_lesson
                ON transcripts(lesson_id, language, source_kind, version);
            CREATE INDEX IF NOT EXISTS idx_attachments_course
                ON attachments(course_id, lesson_id);
            """
        )

    def health(self) -> dict[str, Any]:
        with self.connect() as conn:
            version = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] or 0
            fts = conn.execute("SELECT count(*) FROM transcript_fts").fetchone()[0]
            variants = conn.execute("SELECT count(*) FROM transcripts").fetchone()[0]
            attachments = conn.execute("SELECT count(*) FROM attachments").fetchone()[0]
        return {
            "database": "ok",
            "schema_version": version,
            "fts_rows": fts,
            "transcript_variants": variants,
            "attachments": attachments,
        }

    def sync_library(self, download_root: Path) -> dict[str, Any]:
        discovered = build_library(download_root)
        now = _now()
        with self.connect() as conn:
            for course in discovered["courses"]:
                conn.execute(
                    """INSERT INTO courses(id,title,directory,created_at,updated_at)
                       VALUES(?,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET title=excluded.title,directory=excluded.directory,updated_at=excluded.updated_at""",
                    (course["id"], course["title"], course["directory"], now, now),
                )
                groups: dict[str, list[dict[str, Any]]] = {}
                for transcript in course["lessons"]:
                    groups.setdefault(_logical_transcript_key(transcript["transcript_path"]), []).append(transcript)

                lesson_rows: list[dict[str, Any]] = []
                for position, variants in enumerate(groups.values(), start=1):
                    variants.sort(key=lambda item: item["transcript_path"].lower())
                    primary = variants[0]
                    metadata = self._metadata_for(download_root, primary["transcript_path"])
                    lesson_title = metadata.get("title") or primary["title"]
                    course_title = metadata.get("playlist_title")
                    if course_title:
                        conn.execute(
                            "UPDATE courses SET title=?,source_platform=?,source_url=?,updated_at=? WHERE id=?",
                            (
                                course_title,
                                metadata.get("extractor_key") or metadata.get("extractor"),
                                metadata.get("playlist_webpage_url"),
                                now,
                                course["id"],
                            ),
                        )
                    section_title, section_position = self._section_for(primary["transcript_path"], metadata)
                    section_id = _sha(f"section:{course['id']}:{section_title.casefold()}")[:24]
                    conn.execute(
                        """INSERT INTO sections(id,course_id,title,position)
                           VALUES(?,?,?,?)
                           ON CONFLICT(id) DO UPDATE SET title=excluded.title,position=excluded.position""",
                        (section_id, course["id"], section_title, section_position),
                    )
                    source_url = metadata.get("webpage_url") or metadata.get("original_url")
                    platform = metadata.get("extractor_key") or metadata.get("extractor")
                    lesson_id = primary["id"]
                    conn.execute(
                        """INSERT INTO lessons(
                               id,course_id,section_id,title,position,source_platform,source_url,source_id,media_path,
                               transcript_path,transcript_format,language,duration,uploader,thumbnail,created_at,updated_at
                           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(id) DO UPDATE SET
                               course_id=excluded.course_id,section_id=excluded.section_id,title=excluded.title,position=excluded.position,
                               source_platform=excluded.source_platform,source_url=excluded.source_url,source_id=excluded.source_id,
                               media_path=excluded.media_path,transcript_path=excluded.transcript_path,
                               transcript_format=excluded.transcript_format,language=excluded.language,duration=excluded.duration,
                               uploader=excluded.uploader,thumbnail=excluded.thumbnail,updated_at=excluded.updated_at""",
                        (
                            lesson_id, course["id"], section_id, lesson_title,
                            metadata.get("playlist_index") or position,
                            platform, source_url, metadata.get("id"), primary.get("media_path"),
                            primary["transcript_path"], primary["transcript_format"], primary.get("language"),
                            metadata.get("duration"), metadata.get("uploader") or metadata.get("channel"),
                            metadata.get("thumbnail"), now, now,
                        ),
                    )
                    for variant in variants:
                        variant_metadata = self._metadata_for(download_root, variant["transcript_path"])
                        self._sync_transcript(conn, download_root, lesson_id, variant, variant_metadata)
                    lesson_rows.append(
                        {
                            "id": lesson_id,
                            "parent": Path(primary["transcript_path"]).parent.as_posix(),
                            "title": lesson_title,
                        }
                    )
                self._sync_attachments(conn, download_root, course, lesson_rows)
        return self.library()

    def _sync_transcript(
        self,
        conn: sqlite3.Connection,
        root: Path,
        lesson_id: str,
        transcript: dict[str, Any],
        metadata: dict[str, Any],
    ) -> None:
        parsed = load_transcript(root, transcript["transcript_path"])
        content_hash = _sha(parsed["text"])
        language = transcript.get("language") or "und"
        source_kind = self._source_kind(metadata, language)
        transcript_id = _sha(f"transcript:{lesson_id}:{transcript['transcript_path']}")[:24]
        existing = conn.execute("SELECT content_hash FROM transcripts WHERE id=?", (transcript_id,)).fetchone()
        provenance = {
            "path": transcript["transcript_path"],
            "source_url": metadata.get("webpage_url") or metadata.get("original_url"),
            "extractor": metadata.get("extractor_key") or metadata.get("extractor"),
            "source_id": metadata.get("id"),
        }
        now = _now()
        conn.execute(
            """INSERT INTO transcripts(
                   id,lesson_id,path,format,language,source_kind,provenance_json,version,
                   content_hash,word_count,has_timestamps,created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                   lesson_id=excluded.lesson_id,path=excluded.path,format=excluded.format,language=excluded.language,
                   source_kind=excluded.source_kind,provenance_json=excluded.provenance_json,
                   content_hash=excluded.content_hash,word_count=excluded.word_count,
                   has_timestamps=excluded.has_timestamps,updated_at=excluded.updated_at""",
            (
                transcript_id, lesson_id, transcript["transcript_path"], parsed["format"], language,
                source_kind, json.dumps(provenance, sort_keys=True), 1, content_hash, parsed["word_count"],
                1 if parsed["has_timestamps"] else 0, now, now,
            ),
        )
        if existing and existing["content_hash"] == content_hash:
            return
        conn.execute("DELETE FROM transcript_segments WHERE transcript_id=?", (transcript_id,))
        conn.execute("DELETE FROM transcript_fts WHERE transcript_id=?", (transcript_id,))
        for index, segment in enumerate(parsed["segments"]):
            conn.execute(
                "INSERT INTO transcript_segments(transcript_id,lesson_id,segment_index,start_ms,end_ms,text) VALUES(?,?,?,?,?,?)",
                (transcript_id, lesson_id, index, segment.get("start"), segment.get("end"), segment["text"]),
            )
            conn.execute(
                "INSERT INTO transcript_fts(text,transcript_id,lesson_id,start_ms,end_ms) VALUES(?,?,?,?,?)",
                (segment["text"], transcript_id, lesson_id, segment.get("start"), segment.get("end")),
            )

    def _sync_attachments(
        self,
        conn: sqlite3.Connection,
        root: Path,
        course: dict[str, Any],
        lessons: list[dict[str, Any]],
    ) -> None:
        course_root = root if course["directory"] == "Ungrouped" else root / course["directory"]
        if not course_root.exists():
            return
        conn.execute("DELETE FROM attachments WHERE course_id=?", (course["id"],))
        for path in sorted(course_root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if any(part.startswith(".") for part in rel.parts):
                continue
            lower = path.name.lower()
            if path.suffix.lower() in TRANSCRIPT_EXTENSIONS or path.suffix.lower() in MEDIA_EXTENSIONS:
                continue
            if lower.endswith(".info.json") or lower.endswith((".part", ".ytdl", ".tmp")):
                continue
            lesson_id = None
            parent = rel.parent.as_posix()
            same_parent = [item for item in lessons if item["parent"] == parent]
            if len(same_parent) == 1:
                lesson_id = same_parent[0]["id"]
            attachment_id = _sha(f"attachment:{rel.as_posix()}")[:24]
            stat = path.stat()
            conn.execute(
                """INSERT INTO attachments(
                       id,course_id,lesson_id,filename,relative_path,mime_type,size,source_url,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    attachment_id, course["id"], lesson_id, path.name, rel.as_posix(),
                    mimetypes.guess_type(path.name)[0], stat.st_size, None, _now(), _now(),
                ),
            )

    def library(self) -> dict[str, Any]:
        with self.connect() as conn:
            courses = [
                dict(row)
                for row in conn.execute(
                    "SELECT id,title,directory,source_platform,source_url FROM courses ORDER BY lower(title)"
                )
            ]
            for course in courses:
                sections = [
                    dict(row)
                    for row in conn.execute(
                        "SELECT id,title,position FROM sections WHERE course_id=? ORDER BY COALESCE(position,999999),lower(title)",
                        (course["id"],),
                    )
                ]
                lessons = [
                    dict(row)
                    for row in conn.execute(
                        """SELECT id,section_id,title,position,source_platform,source_url,source_id,media_path,transcript_path,
                                  transcript_format,language,duration,uploader,thumbnail
                           FROM lessons WHERE course_id=? ORDER BY COALESCE(position,999999), lower(title)""",
                        (course["id"],),
                    )
                ]
                for lesson in lessons:
                    lesson["transcripts"] = self._transcripts_for_lesson_conn(conn, lesson["id"])
                    lesson["attachments"] = [
                        dict(row)
                        for row in conn.execute(
                            """SELECT id,filename,relative_path,mime_type,size,source_url
                               FROM attachments WHERE lesson_id=? ORDER BY lower(filename)""",
                            (lesson["id"],),
                        )
                    ]
                section_map = {section["id"]: section for section in sections}
                for section in sections:
                    section["lessons"] = []
                for lesson in lessons:
                    section = section_map.get(lesson["section_id"])
                    if section is not None:
                        section["lessons"].append(lesson)
                course["sections"] = sections
                course["lessons"] = lessons
                course["attachments"] = [
                    dict(row)
                    for row in conn.execute(
                        """SELECT id,lesson_id,filename,relative_path,mime_type,size,source_url
                           FROM attachments WHERE course_id=? ORDER BY lower(filename)""",
                        (course["id"],),
                    )
                ]
                course["lesson_count"] = len(lessons)
        return {
            "courses": courses,
            "course_count": len(courses),
            "lesson_count": sum(c["lesson_count"] for c in courses),
        }

    def course(self, course_id: str) -> dict[str, Any]:
        library = self.library()
        for course in library["courses"]:
            if course["id"] == course_id:
                return course
        raise KeyError(course_id)

    def lesson(self, lesson_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """SELECT id,course_id,section_id,title,position,source_platform,source_url,source_id,media_path,
                          transcript_path,transcript_format,language,duration,uploader,thumbnail
                   FROM lessons WHERE id=?""",
                (lesson_id,),
            ).fetchone()
            if not row:
                raise KeyError(lesson_id)
            lesson = dict(row)
            lesson["transcripts"] = self._transcripts_for_lesson_conn(conn, lesson_id)
            lesson["attachments"] = [
                dict(item)
                for item in conn.execute(
                    "SELECT id,filename,relative_path,mime_type,size,source_url FROM attachments WHERE lesson_id=? ORDER BY lower(filename)",
                    (lesson_id,),
                )
            ]
            return lesson

    def transcripts_for_lesson(self, lesson_id: str) -> list[dict[str, Any]]:
        self._require_lesson(lesson_id)
        with self.connect() as conn:
            return self._transcripts_for_lesson_conn(conn, lesson_id)

    def _transcripts_for_lesson_conn(self, conn: sqlite3.Connection, lesson_id: str) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """SELECT id,path,format,language,source_kind,provenance_json,version,word_count,has_timestamps,created_at,updated_at
                   FROM transcripts WHERE lesson_id=? ORDER BY language,source_kind,version""",
                (lesson_id,),
            )
        ]

    def transcript(self, transcript_id: str, *, include_segments: bool = True) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """SELECT id,lesson_id,path,format,language,source_kind,provenance_json,version,
                          word_count,has_timestamps,created_at,updated_at
                   FROM transcripts WHERE id=?""",
                (transcript_id,),
            ).fetchone()
            if not row:
                raise KeyError(transcript_id)
            payload = dict(row)
            try:
                payload["provenance"] = json.loads(payload.pop("provenance_json"))
            except (TypeError, ValueError, json.JSONDecodeError):
                payload["provenance"] = {}
            if include_segments:
                payload["segments"] = [
                    dict(segment)
                    for segment in conn.execute(
                        """SELECT segment_index,start_ms,end_ms,text
                           FROM transcript_segments WHERE transcript_id=? ORDER BY segment_index""",
                        (transcript_id,),
                    )
                ]
            return payload

    def search(
        self,
        query: str,
        *,
        course_id: str | None = None,
        lesson_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        query = query.strip()
        if not query:
            return {"query": query, "hits": [], "count": 0}
        limit = max(1, min(int(limit), 200))
        sql = """
            SELECT f.transcript_id,f.lesson_id,f.start_ms,f.end_ms,
                   snippet(transcript_fts,0,'<mark>','</mark>','…',20) AS snippet,
                   l.title AS lesson_title,l.transcript_path,c.id AS course_id,c.title AS course_title,
                   t.language,t.source_kind
            FROM transcript_fts f
            JOIN transcripts t ON t.id=f.transcript_id
            JOIN lessons l ON l.id=f.lesson_id
            JOIN courses c ON c.id=l.course_id
            WHERE transcript_fts MATCH ?
        """
        params: list[Any] = [query]
        if lesson_id:
            sql += " AND l.id=?"
            params.append(lesson_id)
        if course_id:
            sql += " AND c.id=?"
            params.append(course_id)
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            try:
                rows = [dict(row) for row in conn.execute(sql, params)]
            except sqlite3.OperationalError:
                quoted = '"' + query.replace('"', '""') + '"'
                params[0] = quoted
                rows = [dict(row) for row in conn.execute(sql, params)]
        return {"query": query, "hits": rows, "count": len(rows)}

    def get_progress(self, lesson_id: str) -> dict[str, Any]:
        self._require_lesson(lesson_id)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT lesson_id,last_position_ms,completed,updated_at FROM study_progress WHERE lesson_id=?",
                (lesson_id,),
            ).fetchone()
        return dict(row) if row else {"lesson_id": lesson_id, "last_position_ms": 0, "completed": 0, "updated_at": None}

    def put_progress(self, lesson_id: str, last_position_ms: int, completed: bool = False) -> dict[str, Any]:
        self._require_lesson(lesson_id)
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO study_progress(lesson_id,last_position_ms,completed,updated_at)
                   VALUES(?,?,?,?)
                   ON CONFLICT(lesson_id) DO UPDATE SET
                       last_position_ms=excluded.last_position_ms,completed=excluded.completed,updated_at=excluded.updated_at""",
                (lesson_id, max(0, int(last_position_ms)), 1 if completed else 0, _now()),
            )
        return self.get_progress(lesson_id)

    def get_note(self, lesson_id: str) -> dict[str, Any]:
        self._require_lesson(lesson_id)
        with self.connect() as conn:
            row = conn.execute("SELECT lesson_id,body,created_at,updated_at FROM notes WHERE lesson_id=?", (lesson_id,)).fetchone()
        return dict(row) if row else {"lesson_id": lesson_id, "body": "", "created_at": None, "updated_at": None}

    def put_note(self, lesson_id: str, body: str) -> dict[str, Any]:
        self._require_lesson(lesson_id)
        now = _now()
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO notes(lesson_id,body,created_at,updated_at) VALUES(?,?,?,?)
                   ON CONFLICT(lesson_id) DO UPDATE SET body=excluded.body,updated_at=excluded.updated_at""",
                (lesson_id, body, now, now),
            )
        return self.get_note(lesson_id)

    def bookmarks(self, lesson_id: str) -> list[dict[str, Any]]:
        self._require_lesson(lesson_id)
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(
                "SELECT id,lesson_id,segment_index,start_ms,end_ms,text,created_at FROM bookmarks WHERE lesson_id=? ORDER BY COALESCE(start_ms,0),segment_index",
                (lesson_id,),
            )]

    def add_bookmark(self, lesson_id: str, segment_index: int, start_ms: int | None, end_ms: int | None, text: str) -> dict[str, Any]:
        self._require_lesson(lesson_id)
        bookmark_id = _sha(f"{lesson_id}:{segment_index}")[:24]
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO bookmarks(id,lesson_id,segment_index,start_ms,end_ms,text,created_at) VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(lesson_id,segment_index) DO UPDATE SET start_ms=excluded.start_ms,end_ms=excluded.end_ms,text=excluded.text""",
                (bookmark_id, lesson_id, segment_index, start_ms, end_ms, text[:4000], _now()),
            )
            row = conn.execute("SELECT * FROM bookmarks WHERE id=?", (bookmark_id,)).fetchone()
        return dict(row)

    def delete_bookmark(self, bookmark_id: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM bookmarks WHERE id=?", (bookmark_id,))
            return cur.rowcount > 0

    def _require_lesson(self, lesson_id: str) -> None:
        with self.connect() as conn:
            row = conn.execute("SELECT 1 FROM lessons WHERE id=?", (lesson_id,)).fetchone()
        if not row:
            raise KeyError(lesson_id)

    @staticmethod
    def _section_for(transcript_path: str, metadata: dict[str, Any]) -> tuple[str, int]:
        title = metadata.get("section_title") or metadata.get("chapter") or metadata.get("chapter_title") or metadata.get("section")
        position = metadata.get("section_number") or metadata.get("chapter_number") or 1
        if not title:
            parts = Path(transcript_path).parts
            title = parts[-2] if len(parts) > 2 else "Course content"
        try:
            position = int(position)
        except (TypeError, ValueError):
            position = 1
        return str(title), position

    @staticmethod
    def _source_kind(metadata: dict[str, Any], language: str) -> str:
        subtitles = metadata.get("subtitles") or {}
        automatic = metadata.get("automatic_captions") or {}
        if language in subtitles:
            return "manual"
        if language in automatic:
            return "auto"
        return "imported"

    @staticmethod
    def _metadata_for(root: Path, transcript_path: str) -> dict[str, Any]:
        path = (root / transcript_path).resolve()
        candidates = []
        base = path.name
        for suffix in (".vtt", ".srt", ".json3", ".txt", ".md"):
            if base.lower().endswith(suffix):
                base = base[: -len(suffix)]
                break
        parts = base.split(".")
        if len(parts) > 1 and len(parts[-1]) in {2, 3, 5, 6, 7}:
            base = ".".join(parts[:-1])
        candidates.append(path.with_name(base + ".info.json"))
        candidates.extend(sorted(path.parent.glob("*.info.json")))
        for candidate in candidates:
            if not candidate.is_file():
                continue
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8", errors="replace"))
                return payload if isinstance(payload, dict) else {}
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        return {}
