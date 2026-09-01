import json
import tempfile
import unittest
from pathlib import Path

from app.api_v1 import build_api_v1
from app.database import CourseStore
from app.transcript_export import export_transcript


VTT = """WEBVTT\n\n00:00:01.000 --> 00:00:03.250\nFirst synchronized segment.\n\n00:00:04.000 --> 00:00:07.500\nSecond synchronized segment.\n"""


class ApiV1Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.downloads = root / "downloads"
        self.data = root / "data"
        course = self.downloads / "ViewerCourse"
        course.mkdir(parents=True)
        (course / "001 Viewer.en.vtt").write_text(VTT, encoding="utf-8")
        (course / "001 Viewer.mp4").write_bytes(b"fixture-media")
        (course / "001 Viewer.info.json").write_text(
            json.dumps({
                "id": "viewer-fixture",
                "title": "Viewer lesson",
                "playlist_title": "Viewer Course",
                "playlist_index": 1,
                "webpage_url": "https://www.youtube.com/watch?v=viewer-fixture",
                "extractor_key": "Youtube",
                "subtitles": {"en": []},
            }),
            encoding="utf-8",
        )
        self.store = CourseStore(self.data / "app.db")

    def tearDown(self):
        self.temp.cleanup()

    def test_course_lesson_transcript_progress_and_export_contract(self):
        payload = self.store.sync_library(self.downloads)
        lesson = payload["courses"][0]["lessons"][0]
        self.assertEqual(lesson["media_path"], "ViewerCourse/001 Viewer.mp4")
        self.assertFalse(Path(lesson["media_path"]).is_absolute())
        transcript_id = lesson["transcripts"][0]["id"]

        lesson_payload = self.store.lesson(lesson["id"])
        self.assertEqual(lesson_payload["transcripts"][0]["language"], "en")

        transcript = self.store.transcript(transcript_id)
        self.assertEqual(len(transcript["segments"]), 2)
        matching = [item for item in transcript["segments"] if "second" in item["text"].casefold()]
        self.assertEqual(len(matching), 1)

        progress = self.store.put_progress(lesson["id"], 4321, completed=True)
        self.assertEqual(progress["last_position_ms"], 4321)
        self.assertEqual(self.store.get_progress(lesson["id"])["completed"], 1)

        for output_format in ("txt", "json", "srt", "vtt"):
            body, media_type, extension = export_transcript(transcript, output_format)
            self.assertEqual(extension, output_format)
            self.assertTrue(media_type)
            self.assertTrue(body)
            self.assertNotIn(str(self.downloads), body)

    def test_router_declares_versioned_contract_without_extra_http_test_dependency(self):
        router = build_api_v1(self.store, self.downloads)
        routes = {(route.path, method) for route in router.routes for method in (route.methods or set())}
        expected = {
            ("/api/v1/courses", "GET"),
            ("/api/v1/courses/{course_id}", "GET"),
            ("/api/v1/lessons/{lesson_id}", "GET"),
            ("/api/v1/lessons/{lesson_id}/progress", "GET"),
            ("/api/v1/lessons/{lesson_id}/progress", "PUT"),
            ("/api/v1/transcripts/{transcript_id}", "GET"),
            ("/api/v1/transcripts/{transcript_id}/search", "GET"),
            ("/api/v1/transcripts/{transcript_id}/export", "GET"),
        }
        self.assertTrue(expected.issubset(routes))

    def test_exporter_formats_preserve_timestamps(self):
        transcript = {
            "id": "t",
            "lesson_id": "l",
            "language": "en",
            "source_kind": "manual",
            "version": 1,
            "provenance": {"source_id": "fixture"},
            "segments": [
                {"segment_index": 0, "start_ms": 1000, "end_ms": 3250, "text": "First"},
                {"segment_index": 1, "start_ms": 4000, "end_ms": 7500, "text": "Second"},
            ],
        }
        srt, _, _ = export_transcript(transcript, "srt")
        vtt, _, _ = export_transcript(transcript, "vtt")
        txt, _, _ = export_transcript(transcript, "txt")
        json_body, _, _ = export_transcript(transcript, "json")
        self.assertIn("00:00:01,000 --> 00:00:03,250", srt)
        self.assertIn("00:00:04.000 --> 00:00:07.500", vtt)
        self.assertEqual(txt, "First\nSecond\n")
        self.assertEqual(json.loads(json_body)["segments"][1]["start_ms"], 4000)

    def test_main_and_viewer_assets_expose_stable_surface(self):
        root = Path(__file__).resolve().parents[1]
        main = (root / "app/main.py").read_text(encoding="utf-8")
        viewer = (root / "app/static/viewer.js").read_text(encoding="utf-8")
        html = (root / "app/static/viewer.html").read_text(encoding="utf-8")
        self.assertIn('openapi_url="/api/v1/openapi.json"', main)
        self.assertIn('app.include_router(build_api_v1(store, DOWNLOAD_DIR))', main)
        self.assertIn('@app.get("/viewer")', main)
        self.assertIn("timeupdate", viewer)
        self.assertIn("scrollIntoView", viewer)
        self.assertIn("/api/v1/transcripts/", viewer)
        self.assertIn("Transcript source", html)
        self.assertIn("Auto-scroll transcript", html)


if __name__ == "__main__":
    unittest.main()
