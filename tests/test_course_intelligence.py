import tempfile
import unittest
from pathlib import Path

from app.learning_library import build_library, load_transcript, search_transcript


ROOT = Path(__file__).resolve().parents[1]


class CourseIntelligenceTests(unittest.TestCase):
    def test_learning_workspace_assets_exist(self):
        for relative in (
            "app/static/learn.html",
            "app/static/learn.css",
            "app/static/learn.js",
            "app/learning_library.py",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_fastapi_exposes_learning_routes(self):
        main = (ROOT / "app/main.py").read_text(encoding="utf-8")
        self.assertIn('@app.get("/learn")', main)
        self.assertIn('@app.get("/api/library")', main)
        self.assertIn('@app.get("/api/learning/transcript")', main)
        self.assertIn('@app.get("/api/learning/search")', main)

    def test_downloader_links_to_course_intelligence(self):
        index = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
        self.assertIn('href="/learn"', index)
        self.assertIn("Course Intelligence", index)

    def test_vtt_transcript_is_grouped_and_parsed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            course = root / "python-course"
            course.mkdir()
            transcript = course / "001 - Variables.en.vtt"
            transcript.write_text(
                "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nVariables store values.\n\n"
                "00:00:03.500 --> 00:00:06.000\nPython infers the value type.\n",
                encoding="utf-8",
            )
            (course / "001 - Variables.mp4").write_bytes(b"media")

            library = build_library(root)
            self.assertEqual(library["course_count"], 1)
            self.assertEqual(library["lesson_count"], 1)
            lesson = library["courses"][0]["lessons"][0]
            self.assertEqual(lesson["language"], "en")
            self.assertEqual(lesson["media_path"], "python-course/001 - Variables.mp4")

            parsed = load_transcript(root, lesson["transcript_path"])
            self.assertTrue(parsed["has_timestamps"])
            self.assertEqual(parsed["segments"][0]["start"], 1000)
            self.assertIn("Variables store values", parsed["text"])

            hits = search_transcript(root, lesson["transcript_path"], "infers")
            self.assertEqual(hits["count"], 1)
            self.assertEqual(hits["hits"][0]["start"], 3500)

    def test_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "downloads"
            root.mkdir()
            outside = Path(temp) / "outside.txt"
            outside.write_text("secret", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_transcript(root, "../outside.txt")

    def test_reverse_engineering_document_records_product_direction(self):
        docs = (ROOT / "docs/YOUTUBE_TRANSCRIPT_DEV_REVERSE_ENGINEERING.md").read_text(encoding="utf-8")
        self.assertIn("Course Intelligence OS", docs)
        self.assertIn("SQLite FTS5", docs)
        self.assertIn("MCP", docs)
        self.assertIn("strict citation contract", docs)


if __name__ == "__main__":
    unittest.main()
