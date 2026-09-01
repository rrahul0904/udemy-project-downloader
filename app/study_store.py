from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STUDY_SCHEMA_VERSION = 3
ARTIFACT_KINDS = {"summary", "notes", "flashcards", "quiz", "concept_map"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


class StudyStore:
    """Study artifact persistence sharing the Course Intelligence SQLite database."""

    def __init__(self, path: Path):
        self.path = Path(path)
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
                CREATE TABLE IF NOT EXISTS study_artifacts (
                    id TEXT PRIMARY KEY,
                    lesson_id TEXT REFERENCES lessons(id) ON DELETE CASCADE,
                    course_id TEXT REFERENCES courses(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    source_transcript_id TEXT NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    content_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(lesson_id, kind, source_transcript_id, version)
                );
                CREATE TABLE IF NOT EXISTS artifact_citations (
                    id TEXT PRIMARY KEY,
                    artifact_id TEXT NOT NULL REFERENCES study_artifacts(id) ON DELETE CASCADE,
                    item_key TEXT NOT NULL,
                    transcript_id TEXT NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
                    segment_index INTEGER NOT NULL,
                    start_ms INTEGER,
                    end_ms INTEGER,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(artifact_id, item_key, transcript_id, segment_index)
                );
                CREATE INDEX IF NOT EXISTS idx_study_artifacts_lesson_kind
                    ON study_artifacts(lesson_id, kind, version);
                CREATE INDEX IF NOT EXISTS idx_artifact_citations_artifact
                    ON artifact_citations(artifact_id, item_key);
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (STUDY_SCHEMA_VERSION, _now()),
            )

    def save_artifact(
        self,
        *,
        lesson_id: str,
        course_id: str,
        kind: str,
        transcript_id: str,
        provider: str,
        model: str,
        content: dict[str, Any],
    ) -> dict[str, Any]:
        if kind not in ARTIFACT_KINDS:
            raise ValueError("Unsupported study artifact kind.")
        with self.connect() as conn:
            version = conn.execute(
                """SELECT COALESCE(MAX(version),0)+1 FROM study_artifacts
                   WHERE lesson_id=? AND kind=? AND source_transcript_id=?""",
                (lesson_id, kind, transcript_id),
            ).fetchone()[0]
            artifact_id = _id(f"artifact:{lesson_id}:{kind}:{transcript_id}:{version}")
            now = _now()
            conn.execute(
                """INSERT INTO study_artifacts(
                       id,lesson_id,course_id,kind,source_transcript_id,provider,model,version,
                       content_json,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    artifact_id, lesson_id, course_id, kind, transcript_id, provider, model, version,
                    json.dumps(content, ensure_ascii=False, sort_keys=True), now, now,
                ),
            )
            citations = list(self._walk_citations(content))
            for item_key, citation in citations:
                citation_id = _id(
                    f"citation:{artifact_id}:{item_key}:{citation['transcript_id']}:{citation['segment_index']}"
                )
                conn.execute(
                    """INSERT OR IGNORE INTO artifact_citations(
                           id,artifact_id,item_key,transcript_id,segment_index,start_ms,end_ms,text,created_at
                       ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        citation_id, artifact_id, item_key, citation["transcript_id"],
                        int(citation["segment_index"]), citation.get("start_ms"), citation.get("end_ms"),
                        str(citation.get("text") or "")[:4000], now,
                    ),
                )
        return self.artifact(artifact_id)

    def artifact(self, artifact_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM study_artifacts WHERE id=?", (artifact_id,)).fetchone()
            if not row:
                raise KeyError(artifact_id)
            payload = self._row(row)
            payload["citations"] = [
                dict(item)
                for item in conn.execute(
                    """SELECT item_key,transcript_id,segment_index,start_ms,end_ms,text
                       FROM artifact_citations WHERE artifact_id=? ORDER BY item_key,segment_index""",
                    (artifact_id,),
                )
            ]
            return payload

    def artifacts(self, lesson_id: str, kind: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM study_artifacts WHERE lesson_id=?"
        params: list[Any] = [lesson_id]
        if kind:
            if kind not in ARTIFACT_KINDS:
                raise ValueError("Unsupported study artifact kind.")
            sql += " AND kind=?"
            params.append(kind)
        sql += " ORDER BY kind, version DESC, created_at DESC"
        with self.connect() as conn:
            return [self._row(row) for row in conn.execute(sql, params)]

    def latest(self, lesson_id: str, kind: str) -> dict[str, Any] | None:
        if kind not in ARTIFACT_KINDS:
            raise ValueError("Unsupported study artifact kind.")
        with self.connect() as conn:
            row = conn.execute(
                """SELECT * FROM study_artifacts WHERE lesson_id=? AND kind=?
                   ORDER BY version DESC,created_at DESC LIMIT 1""",
                (lesson_id, kind),
            ).fetchone()
        return self._row(row) if row else None

    def health(self) -> dict[str, int]:
        with self.connect() as conn:
            artifacts = conn.execute("SELECT count(*) FROM study_artifacts").fetchone()[0]
            citations = conn.execute("SELECT count(*) FROM artifact_citations").fetchone()[0]
        return {"study_schema_version": STUDY_SCHEMA_VERSION, "study_artifacts": artifacts, "artifact_citations": citations}

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload["content"] = json.loads(payload.pop("content_json"))
        return payload

    @classmethod
    def _walk_citations(cls, value: Any, key: str = "root"):
        if isinstance(value, dict):
            citations = value.get("citations")
            if isinstance(citations, list):
                for citation in citations:
                    if cls._valid_citation(citation):
                        yield key, citation
            for child_key, child in value.items():
                if child_key != "citations":
                    yield from cls._walk_citations(child, f"{key}.{child_key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                yield from cls._walk_citations(child, f"{key}[{index}]")

    @staticmethod
    def _valid_citation(value: Any) -> bool:
        return isinstance(value, dict) and {
            "transcript_id", "segment_index", "text"
        }.issubset(value)
