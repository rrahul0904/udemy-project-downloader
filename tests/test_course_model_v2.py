import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.database import CourseStore


VTT_EN = """WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHello from the manual English transcript.\n\n00:00:04.000 --> 00:00:07.000\nSQLite FTS5 durable search.\n"""
VTT_ES = """WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHola desde la transcripción automática.\n\n00:00:04.000 --> 00:00:07.000\nBúsqueda persistente en español.\n"""


class CourseModelV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.downloads = root / "downloads"
        self.data = root / "data"
        self.course = self.downloads / "VariantCourse"
        self.course.mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def _write_variant_fixture(self):
        (self.course / "001 Introduction.en.vtt").write_text(VTT_EN, encoding="utf-8")
        (self.course / "001 Introduction.es.vtt").write_text(VTT_ES, encoding="utf-8")
        (self.course / "handout.pdf").write_bytes(b"%PDF-1.4\nfixture\n")
        info = {
            "id": "fixture-introduction",
            "title": "Introduction",
            "playlist_title": "Variant Course",
            "playlist_index": 1,
            "webpage_url": "https://www.youtube.com/watch?v=fixture-introduction",
            "extractor_key": "Youtube",
            "subtitles": {"en": []},
            "automatic_captions": {"es": []},
            "duration": 14,
        }
        (self.course / "001 Introduction.info.json").write_text(json.dumps(info), encoding="utf-8")

    def test_variant_ingestion_sections_attachments_and_fts(self):
        self._write_variant_fixture()
        store = CourseStore(self.data / "app.db")
        library = store.sync_library(self.downloads)

        self.assertEqual(store.health()["schema_version"], 2)
        self.assertEqual(library["course_count"], 1)
        self.assertEqual(library["lesson_count"], 1)
        course = library["courses"][0]
        self.assertEqual(course["title"], "Variant Course")
        self.assertEqual(len(course["sections"]), 1)
        self.assertEqual(course["sections"][0]["title"], "Course content")
        self.assertEqual(len(course["sections"][0]["lessons"]), 1)

        lesson = course["lessons"][0]
        self.assertEqual(len(lesson["transcripts"]), 2)
        variants = {(item["language"], item["source_kind"]) for item in lesson["transcripts"]}
        self.assertEqual(variants, {("en", "manual"), ("es", "auto")})

        self.assertEqual(len(course["attachments"]), 1)
        attachment = course["attachments"][0]
        self.assertEqual(attachment["filename"], "handout.pdf")
        self.assertEqual(attachment["relative_path"], "VariantCourse/handout.pdf")
        self.assertFalse(Path(attachment["relative_path"]).is_absolute())

        english = store.search("SQLite FTS5")
        spanish = store.search("persistente")
        self.assertEqual(english["count"], 1)
        self.assertEqual(english["hits"][0]["language"], "en")
        self.assertEqual(english["hits"][0]["source_kind"], "manual")
        self.assertTrue(english["hits"][0]["transcript_id"])
        self.assertEqual(spanish["count"], 1)
        self.assertEqual(spanish["hits"][0]["language"], "es")
        self.assertEqual(spanish["hits"][0]["source_kind"], "auto")

    def test_progress_survives_store_reopen(self):
        self._write_variant_fixture()
        store = CourseStore(self.data / "app.db")
        lesson_id = store.sync_library(self.downloads)["courses"][0]["lessons"][0]["id"]
        saved = store.put_progress(lesson_id, 9123, completed=True)
        self.assertEqual(saved["last_position_ms"], 9123)
        self.assertEqual(saved["completed"], 1)

        reopened = CourseStore(self.data / "app.db")
        progress = reopened.get_progress(lesson_id)
        self.assertEqual(progress["last_position_ms"], 9123)
        self.assertEqual(progress["completed"], 1)

    def test_v1_migration_preserves_transcript_segments_notes_and_bookmarks(self):
        db = self.data / "app.db"
        db.parent.mkdir(parents=True)
        conn = sqlite3.connect(db)
        conn.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
            INSERT INTO schema_migrations VALUES(1,'legacy');
            CREATE TABLE courses (
                id TEXT PRIMARY KEY,title TEXT NOT NULL,directory TEXT NOT NULL UNIQUE,
                source_platform TEXT,source_url TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL
            );
            CREATE TABLE sections (
                id TEXT PRIMARY KEY,course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                title TEXT NOT NULL,position INTEGER,UNIQUE(course_id,title)
            );
            CREATE TABLE lessons (
                id TEXT PRIMARY KEY,course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                section_id TEXT REFERENCES sections(id) ON DELETE SET NULL,title TEXT NOT NULL,position INTEGER,
                source_platform TEXT,source_url TEXT,source_id TEXT,media_path TEXT,
                transcript_path TEXT NOT NULL UNIQUE,transcript_format TEXT NOT NULL,language TEXT,
                duration REAL,uploader TEXT,thumbnail TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL
            );
            CREATE TABLE transcripts (
                id TEXT PRIMARY KEY,lesson_id TEXT NOT NULL UNIQUE REFERENCES lessons(id) ON DELETE CASCADE,
                path TEXT NOT NULL UNIQUE,format TEXT NOT NULL,language TEXT,content_hash TEXT NOT NULL,
                word_count INTEGER NOT NULL,has_timestamps INTEGER NOT NULL,updated_at TEXT NOT NULL
            );
            CREATE TABLE transcript_segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,transcript_id TEXT NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
                lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,segment_index INTEGER NOT NULL,
                start_ms INTEGER,end_ms INTEGER,text TEXT NOT NULL,UNIQUE(transcript_id,segment_index)
            );
            CREATE VIRTUAL TABLE transcript_fts USING fts5(
                text,transcript_id UNINDEXED,lesson_id UNINDEXED,start_ms UNINDEXED,end_ms UNINDEXED,tokenize='unicode61'
            );
            CREATE TABLE notes (
                lesson_id TEXT PRIMARY KEY REFERENCES lessons(id) ON DELETE CASCADE,body TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,updated_at TEXT NOT NULL
            );
            CREATE TABLE bookmarks (
                id TEXT PRIMARY KEY,lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
                segment_index INTEGER NOT NULL,start_ms INTEGER,end_ms INTEGER,text TEXT NOT NULL,created_at TEXT NOT NULL,
                UNIQUE(lesson_id,segment_index)
            );
            CREATE TABLE study_progress (
                lesson_id TEXT PRIMARY KEY REFERENCES lessons(id) ON DELETE CASCADE,last_position_ms INTEGER,
                completed INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL
            );
            INSERT INTO courses VALUES('c','Legacy','Legacy',NULL,NULL,'t','t');
            INSERT INTO lessons VALUES('l','c',NULL,'Legacy lesson',1,NULL,NULL,NULL,NULL,'Legacy/a.en.vtt','vtt','en',NULL,NULL,NULL,'t','t');
            INSERT INTO transcripts VALUES('tr','l','Legacy/a.en.vtt','vtt','en','hash',2,1,'t');
            INSERT INTO transcript_segments(transcript_id,lesson_id,segment_index,start_ms,end_ms,text)
                VALUES('tr','l',0,1000,2000,'legacy segment');
            INSERT INTO transcript_fts VALUES('legacy segment','tr','l',1000,2000);
            INSERT INTO notes VALUES('l','keep me','t','t');
            INSERT INTO bookmarks VALUES('b','l',0,1000,2000,'legacy segment','t');
            """
        )
        conn.commit()
        conn.close()

        store = CourseStore(db)
        self.assertEqual(store.health()["schema_version"], 2)
        self.assertEqual(store.get_note("l")["body"], "keep me")
        self.assertEqual(store.bookmarks("l")[0]["id"], "b")
        transcript = store.transcript("tr")
        self.assertEqual(transcript["source_kind"], "imported")
        self.assertEqual(transcript["segments"][0]["text"], "legacy segment")
        search = store.search("legacy")
        self.assertEqual(search["count"], 1)
        self.assertEqual(search["hits"][0]["transcript_id"], "tr")


if __name__ == "__main__":
    unittest.main()
