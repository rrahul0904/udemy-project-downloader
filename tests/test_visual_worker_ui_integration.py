"""API regression: CLI-produced visual packages must be visible in lesson UI.

No YouTube access, no Whisper model, and no FFmpeg are required.
"""
import json
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api_v1 import build_api_v1
from app.database import CourseStore


class VisualWorkerUiIntegrationTest(unittest.TestCase):
    def test_worker_visual_manifest_available_without_rerunning_analyzer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            downloads = root / "downloads"
            lesson_folder = downloads / "fYgggzLEIFs-da2b3186"
            lesson_folder.mkdir(parents=True)
            stem = "Snowflake_CoCo [fYgggzLEIFs]"
            media = lesson_folder / (stem + ".mp4")
            media.write_bytes(b"synthetic mp4")
            transcript = lesson_folder / (stem + ".en.vtt")
            transcript.write_text(
                "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nSnowflake cost intelligence.\n",
                encoding="utf-8"
            )
            package = lesson_folder / ("." + stem + ".en.learning") / "visuals"
            frame = package / "frames" / "periodic-0001.jpg"
            frame.parent.mkdir(parents=True)
            frame.write_bytes(b"dummy-jpeg")
            manifest = {
                "status": "frames_with_ocr_unverified",
                "frames_examined": 1,
                "items": [{
                    "timestamp_ms": 1000,
                    "frame_file": "frames/periodic-0001.jpg",
                    "category": "slide_candidate",
                    "ocr": {"status": "completed", "text": "Snowflake cost intelligence", "confidence": 85.0}
                }],
            }
            (package / "visual-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            store = CourseStore(root / "data" / "app.db")
            library = store.sync_library(downloads)
            self.assertEqual(library["lesson_count"], 1)
            lesson_id = library["courses"][0]["lessons"][0]["id"]
            app = FastAPI()
            app.include_router(build_api_v1(store, downloads))
            with TestClient(app) as client:
                response = client.get(f"/api/v1/lessons/{lesson_id}/visuals")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["frames_examined"], 1)
                self.assertEqual(response.json()["items"][0]["ocr"]["text"], "Snowflake cost intelligence")
                response = client.get(f"/api/v1/lessons/{lesson_id}/visuals/frame/periodic-0001.jpg")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, b"dummy-jpeg")
                self.assertEqual(
                    client.get(f"/api/v1/lessons/{lesson_id}/visuals/frame/secrets.txt").status_code,
                    404,
                )

    def test_does_not_expose_unrelated_learning_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            downloads = root / "downloads"
            folder = downloads / "course"
            folder.mkdir(parents=True)
            media = folder / "lesson.mp4"
            media.write_bytes(b"synthetic mp4")
            (folder / "lesson.en.vtt").write_text(
                "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nLesson.\n", encoding="utf-8"
            )
            unrelated = folder / ".unrelated.en.learning" / "visuals"
            unrelated.mkdir(parents=True)
            (unrelated / "visual-manifest.json").write_text(
                json.dumps({"status": "fake", "items": []}), encoding="utf-8"
            )
            store = CourseStore(root / "data" / "app.db")
            library = store.sync_library(downloads)
            lesson_id = library["courses"][0]["lessons"][0]["id"]
            app = FastAPI()
            app.include_router(build_api_v1(store, downloads))
            with TestClient(app) as client:
                response = client.get(f"/api/v1/lessons/{lesson_id}/visuals")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["status"], "not_started")


if __name__ == "__main__":
    unittest.main()
