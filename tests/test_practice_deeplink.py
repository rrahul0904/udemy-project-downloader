"""Regression coverage for real quiz deep-link handling without live Udemy access."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.practice_tests import (
    _discover_course,
    _is_udemy_login_redirect,
    _quiz_id_from_url,
    export_practice_tests,
)

CLAUDE_QUIZ_URL = (
    "https://www.udemy.com/course/anthropic-claude-certified-architect-"
    "3-full-practice-exams/learn/quiz/7570481#overview"
)


class PracticeDeepLinkTests(unittest.TestCase):
    def test_quiz_id_is_read_from_specific_learner_url_only(self):
        self.assertEqual(_quiz_id_from_url(CLAUDE_QUIZ_URL), "7570481")
        self.assertIsNone(_quiz_id_from_url("https://www.udemy.com/course/example/"))
        self.assertIsNone(_quiz_id_from_url("https://www.udemy.com/course/example/learn/quiz/no-id"))

    def test_login_redirect_gets_actionable_warning(self):
        response = MagicMock(
            status_code=200,
            url="https://www.udemy.com/join/passwordless-auth/?action=login",
            text='<script>window.courseId=123</script>',
        )
        session = MagicMock()
        session.get.return_value = response
        course_id, title, warnings = _discover_course(session, CLAUDE_QUIZ_URL)
        self.assertIsNone(course_id)
        self.assertIsNone(title)
        self.assertIn("sign-in", " ".join(warnings).lower())
        self.assertTrue(_is_udemy_login_redirect(response.url))
        self.assertFalse(_is_udemy_login_redirect("https://eviludemy.com/login"))

    def test_export_uses_direct_quiz_id_when_curriculum_is_inaccessible(self):
        assessments = [
            {"prompt": {"question": "Example synthetic question", "answers": ["Option A", "Option B"]}}
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "exams"
            with (
                patch("app.practice_tests._build_session", return_value=MagicMock()),
                patch("app.practice_tests._discover_course", return_value=(None, None, ["Course page required login."])),
                patch("app.practice_tests._fetch_assessments", return_value=(assessments, [])) as fetch,
            ):
                result = export_practice_tests(CLAUDE_QUIZ_URL, Path(tmp) / "dummy-cookies.txt", out_dir)
            self.assertEqual(result.item_count, 1)
            self.assertEqual(result.assessment_count, 1)
            self.assertEqual(result.validation["status"], "partial")
            fetch.assert_called_once()
            self.assertEqual(fetch.call_args.args[2], "7570481")
            data = json.loads(result.output_json.read_text(encoding="utf-8"))
            self.assertEqual(data["practice_tests"][0]["id"], "7570481")
            self.assertEqual(data["practice_tests"][0]["assessments"], assessments)
            self.assertTrue(data["warnings"])

    def test_inaccessible_direct_quiz_stays_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("app.practice_tests._build_session", return_value=MagicMock()),
                patch("app.practice_tests._discover_course", return_value=(None, None, ["Login required."])),
                patch("app.practice_tests._fetch_assessments", return_value=([], ["HTTP 403."])),
            ):
                result = export_practice_tests(
                    CLAUDE_QUIZ_URL, Path(tmp) / "dummy-cookies.txt", Path(tmp) / "exports"
                )
            self.assertEqual(result.item_count, 1)
            self.assertEqual(result.assessment_count, 0)
            self.assertEqual(result.validation["status"], "not_accessible")
            self.assertIn("HTTP 403.", result.warnings)

    def test_linked_quiz_is_not_duplicated_when_already_in_curriculum(self):
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("app.practice_tests._build_session", return_value=MagicMock()),
                patch("app.practice_tests._discover_course", return_value=("123", "Test Course", [])),
                patch("app.practice_tests._fetch_curriculum", return_value=(
                    [{"_class": "quiz", "id": 7570481, "title": "Practice Exam 1"}], []
                )),
                patch("app.practice_tests._fetch_assessments", return_value=([{"prompt": "Q"}], [])),
            ):
                result = export_practice_tests(
                    CLAUDE_QUIZ_URL, Path(tmp) / "dummy-cookies.txt", Path(tmp) / "exports"
                )
            self.assertEqual(result.item_count, 1)

    def test_practice_only_checkbox_is_sent_when_unchecked(self):
        js = (Path(__file__).parent.parent / "app" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('"include_practice_tests", "download_videos", "confirm_authorized"', js)


if __name__ == "__main__":
    unittest.main()
