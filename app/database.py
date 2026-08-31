from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .learning_library import build_library, load_transcript

SCHEMA_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, _now()),
            )

    def health(self) -> dict[str, Any]:
        with self.connect() as conn:
            version = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] or 0
            fts = conn.execute("SELECT count(*) FROM transcript_fts").fetchone()[0]
        return {"database": "ok", "schema_version": version, "fts_rows": fts}

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
                for position, lesson in enumerate(course["lessons"], start=1):
                    metadata = self._metadata_for(download_root, lesson["transcript_path"])
                    lesson_title = metadata.get("title") or lesson["title"]
                    course_title = metadata.get("playlist_title")
                    if course_title:
                        conn.execute("UPDATE courses SET title=?,updated_at=? WHERE id=?", (course_title, now, course["id"]))
                    source_url = metadata.get("webpage_url") or metadata.get("original_url")
                    platform = metadata.get("extractor_key") or metadata.get("extractor")
                    conn.execute(
                        """INSERT INTO lessons(
                               id,course_id,title,position,source_platform,source_url,source_id,media_path,
                               transcript_path,transcript_format,language,duration,uploader,thumbnail,created_at,updated_at
                           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(id) DO UPDATE SET
                               course_id=excluded.course_id,title=excluded.title,position=excluded.position,
                               source_platform=excluded.source_platform,source_url=excluded.source_url,source_id=excluded.source_id,
                               media_path=excluded.media_path,transcript_path=excluded.transcript_path,
                               transcript_format=excluded.transcript_format,language=excluded.language,duration=excluded.duration,
                               uploader=excluded.uploader,thumbnail=excluded.thumbnail,updated_at=excluded.updated_at""",
                        (
                            lesson["id"], course["id"], lesson_title,
                            metadata.get("playlist_index") or position,
                            platform, source_url, metadata.get("id"), lesson.get("media_path"),
                            lesson["transcript_path"], lesson["transcript_format"], lesson.get("language"),
                            metadata.get("duration"), metadata.get("uploader") or metadata.get("channel"),
                            metadata.get("thumbnail"), now, now,
                        ),
                    )
                    self._sync_transcript(conn, download_root, lesson)
        return self.library()

    def _sync_transcript(self, conn: sqlite3.Connection, root: Path, lesson: dict[str, Any]) -> None:
        parsed = load_transcript(root, lesson["transcript_path"])
        content_hash = _sha(parsed["text"])
        transcript_id = _sha(f"transcript:{lesson['id']}")[:24]
        existing = conn.execute("SELECT content_hash FROM transcripts WHERE id=?", (transcript_id,)).fetchone()
        conn.execute(
            """INSERT INTO transcripts(id,lesson_id,path,format,language,content_hash,word_count,has_timestamps,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET path=excluded.path,format=excluded.format,language=excluded.language,
                    content_hash=excluded.content_hash,word_count=excluded.word_count,
                    has_timestamps=excluded.has_timestamps,updated_at=excluded.updated_at""",
            (
                transcript_id, lesson["id"], lesson["transcript_path"], parsed["format"], lesson.get("language"),
                content_hash, parsed["word_count"], 1 if parsed["has_timestamps"] else 0, _now(),
            ),
        )
        if existing and existing["content_hash"] == content_hash:
            return
        conn.execute("DELETE FROM transcript_segments WHERE transcript_id=?", (transcript_id,))
        conn.execute("DELETE FROM transcript_fts WHERE transcript_id=?", (transcript_id,))
        for index, segment in enumerate(parsed["segments"]):
            conn.execute(
                "INSERT INTO transcript_segments(transcript_id,lesson_id,segment_index,start_ms,end_ms,text) VALUES(?,?,?,?,?,?)",
                (transcript_id, lesson["id"], index, segment.get("start"), segment.get("end"), segment["text"]),
            )
            conn.execute(
                "INSERT INTO transcript_fts(text,transcript_id,lesson_id,start_ms,end_ms) VALUES(?,?,?,?,?)",
                (segment["text"], transcript_id, lesson["id"], segment.get("start"), segment.get("end")),
            )

    def library(self) -> dict[str, Any]:
        with self.connect() as conn:
            courses = [dict(row) for row in conn.execute("SELECT id,title,directory,source_platform,source_url FROM courses ORDER BY lower(title)")]
            for course in courses:
                lessons = [dict(row) for row in conn.execute(
                    """SELECT id,title,position,source_platform,source_url,source_id,media_path,transcript_path,
                              transcript_format,language,duration,uploader,thumbnail
                       FROM lessons WHERE course_id=? ORDER BY COALESCE(position,999999), lower(title)""",
                    (course["id"],),
                )]
                course["lessons"] = lessons
                course["lesson_count"] = len(lessons)
        return {
            "courses": courses,
            "course_count": len(courses),
            "lesson_count": sum(c["lesson_count"] for c in courses),
        }

    def search(self, query: str, *, course_id: str | None = None, lesson_id: str | None = None, limit: int = 50) -> dict[str, Any]:
        query = query.strip()
        if not query:
            return {"query": query, "hits": [], "count": 0}
        limit = max(1, min(int(limit), 200))
        sql = """
            SELECT f.lesson_id,f.start_ms,f.end_ms,
                   snippet(transcript_fts,0,'<mark>','</mark>','…',20) AS snippet,
                   l.title AS lesson_title,l.transcript_path,c.id AS course_id,c.title AS course_title
            FROM transcript_fts f
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
