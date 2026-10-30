"""Smoke checks for Course Intelligence visual UI and versioned API wiring."""
import tempfile
import unittest
from pathlib import Path

from app.api_v1 import build_api_v1
from app.database import CourseStore


class VisualApiUiTests(unittest.TestCase):
    def test_visual_endpoints_are_registered(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            router = build_api_v1(CourseStore(root / "data" / "db.sqlite"), root / "downloads")
            routes = {(route.path, method) for route in router.routes for method in (route.methods or ())}
        expected = {
            ("/api/v1/lessons/{lesson_id}/visuals", "POST"),
            ("/api/v1/lessons/{lesson_id}/visuals", "GET"),
            ("/api/v1/lessons/{lesson_id}/visuals/frame/{frame_name}", "GET"),
        }
        self.assertTrue(expected.issubset(routes))

    def test_visual_tab_and_script_integration(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "app/static/learn.html").read_text(encoding="utf-8")
        js = (root / "app/static/learn-visuals.js").read_text(encoding="utf-8")
        css = (root / "app/static/visual-learning.css").read_text(encoding="utf-8")
        self.assertIn('data-tab="visuals"', html)
        self.assertIn('id="tab-visuals"', html)
        self.assertIn('id="visual-analyze"', html)
        self.assertIn('/static/learn-visuals.js', html)
        self.assertIn("ci:lesson-opened", js)
        self.assertIn('method: "POST"', js)
        self.assertIn("visual-disclaimer", css)


if __name__ == "__main__":
    unittest.main()
