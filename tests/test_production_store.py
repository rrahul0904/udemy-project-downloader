import shutil
import tempfile
import unittest
from pathlib import Path

from app.database import CourseStore


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "test-course"


class ProductionCourseStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.downloads = root / "downloads"
        self.data = root / "data"
        target = self.downloads / "TestCourse"
        target.mkdir(parents=True)
        for name in ("001 Introduction.en.vtt", "001 Introduction.info.json"):
            shutil.copy2(FIXTURE / name, target / name)
        self.store = CourseStore(self.data / "app.db")

    def tearDown(self):
        self.temp.cleanup()

    def test_idempotent_ingestion_metadata_and_fts(self):
        first = self.store.sync_library(self.downloads)
        second = self.store.sync_library(self.downloads)
        self.assertEqual(first["course_count"], 1)
        self.assertEqual(first["lesson_count"], 1)
        self.assertEqual(second["lesson_count"], 1)
        course = second["courses"][0]
        lesson = course["lessons"][0]
        self.assertEqual(course["title"], "Production Test Course")
        self.assertEqual(lesson["title"], "Introduction")
        self.assertEqual(lesson["source_id"], "fixture-introduction")
        result = self.store.search("SQLite FTS5")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["hits"][0]["lesson_id"], lesson["id"])
        self.assertEqual(result["hits"][0]["start_ms"], 4000)

    def test_notes_and_bookmarks_survive_store_reopen(self):
        library = self.store.sync_library(self.downloads)
        lesson_id = library["courses"][0]["lessons"][0]["id"]
        self.store.put_note(lesson_id, "Durable personal note")
        bookmark = self.store.add_bookmark(lesson_id, 1, 4000, 9000, "SQLite FTS5")

        reopened = CourseStore(self.data / "app.db")
        self.assertEqual(reopened.get_note(lesson_id)["body"], "Durable personal note")
        bookmarks = reopened.bookmarks(lesson_id)
        self.assertEqual(len(bookmarks), 1)
        self.assertEqual(bookmarks[0]["id"], bookmark["id"])
        self.assertEqual(bookmarks[0]["start_ms"], 4000)
        self.assertTrue(reopened.delete_bookmark(bookmark["id"]))
        self.assertEqual(reopened.bookmarks(lesson_id), [])

    def test_schema_health(self):
        health = self.store.health()
        self.assertEqual(health["database"], "ok")
        self.assertGreaterEqual(health["schema_version"], 1)


if __name__ == "__main__":
    unittest.main()
