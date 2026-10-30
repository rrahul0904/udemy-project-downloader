"""Check the new learning UI and async endpoint contracts without an Ollama server."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from app.api_v1 import build_api_v1
from app.database import CourseStore


class LearningGuideApiUiTests(unittest.TestCase):
    def test_source_grounded_teaching_ui_is_visible(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "app/static/learn.html").read_text(encoding="utf-8")
        js = (root / "app/static/learn-learning-guide.js").read_text(encoding="utf-8")
        css = (root / "app/static/learning-guide.css").read_text(encoding="utf-8")
        self.assertIn('data-tab="learning-guide"', html)
        self.assertIn('id="learning-guide-generate"', html)
        self.assertIn('/static/learn-learning-guide.js', html)
        self.assertIn("How to do it", js)
        self.assertIn("Worked example", js)
        self.assertIn("Worked answer", js)
        self.assertIn("AI draft requiring source review", js)
        self.assertIn("learning-chapter", css)

    def test_learning_job_routes_present_and_missing_model_returns_503(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = CourseStore(root / "data" / "app.db")
            router = build_api_v1(store, root / "downloads")
            routes = {(r.path, method) for r in router.routes for method in (r.methods or ())}
            expected = {
                ("/api/v1/lessons/{lesson_id}/learning-guide/jobs", "POST"),
                ("/api/v1/lessons/{lesson_id}/learning-guide/jobs/{job_id}", "GET"),
            }
            self.assertTrue(expected.issubset(routes))
            start = next(r.endpoint for r in router.routes if
                         r.path.endswith("/{lesson_id}/learning-guide/jobs") and "POST" in r.methods)
            with patch("app.api_v1.learning_model", return_value=""):
                with self.assertRaises(HTTPException) as ctx:
                    asyncio.run(start("unknown-lesson", None))
            self.assertEqual(ctx.exception.status_code, 503)

    def test_inaccessible_job_id_cannot_be_read_for_another_lesson(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            router = build_api_v1(CourseStore(root / "data" / "app.db"), root / "downloads")
            poll = next(r.endpoint for r in router.routes if
                        r.path.endswith("/{lesson_id}/learning-guide/jobs/{job_id}") and "GET" in r.methods)
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(poll("other-lesson", "nonexistent-job"))
            self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
