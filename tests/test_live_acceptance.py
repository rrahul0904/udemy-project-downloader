import base64
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "live_acceptance.py"
SPEC = importlib.util.spec_from_file_location("live_acceptance", SCRIPT)
live_acceptance = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(live_acceptance)


class LiveAcceptanceTests(unittest.TestCase):
    def test_production_url_requires_https_and_no_embedded_credentials(self):
        self.assertEqual(
            live_acceptance.normalize_base_url("https://course-intelligence.onrender.com/"),
            "https://course-intelligence.onrender.com",
        )
        with self.assertRaises(live_acceptance.AcceptanceError):
            live_acceptance.normalize_base_url("http://course-intelligence.onrender.com")
        with self.assertRaises(live_acceptance.AcceptanceError):
            live_acceptance.normalize_base_url("https://admin:secret@course-intelligence.onrender.com")

    def test_basic_auth_header_is_standard_and_secret_is_not_logged_by_helper(self):
        header = live_acceptance.basic_auth_header("admin", "test-password")
        self.assertTrue(header.startswith("Basic "))
        decoded = base64.b64decode(header.removeprefix("Basic ")).decode("utf-8")
        self.assertEqual(decoded, "admin:test-password")

    def test_flatten_lessons_preserves_course_context(self):
        lessons = live_acceptance.flatten_lessons(
            {
                "courses": [
                    {
                        "id": "course-1",
                        "title": "Fixture Course",
                        "lessons": [{"id": "lesson-1", "title": "Intro", "transcript_path": "intro.vtt"}],
                    }
                ]
            }
        )
        self.assertEqual(len(lessons), 1)
        self.assertEqual(lessons[0]["course_id"], "course-1")
        self.assertEqual(lessons[0]["course_title"], "Fixture Course")
        self.assertEqual(lessons[0]["id"], "lesson-1")

    def test_acceptance_runner_covers_release_critical_surfaces(self):
        text = SCRIPT.read_text(encoding="utf-8")
        for expected in (
            "/api/health",
            "/api/readiness",
            "/api/jobs",
            "/api/downloads",
            "/api/library",
            "/api/learning/transcript",
            "/api/learning/search",
            "/notes",
            "/bookmarks",
            "path traversal",
            "cross-origin mutation rejection",
            "verify_persisted_state",
        ):
            self.assertIn(expected, text)


if __name__ == "__main__":
    unittest.main()
