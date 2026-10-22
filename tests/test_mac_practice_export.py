"""Host-side, cookie-file-free Udemy export acceptance with synthetic sessions."""
from __future__ import annotations

import tempfile
import unittest
from http.cookiejar import CookieJar
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from requests.cookies import create_cookie

from app.practice_tests import _session_from_cookiejar, export_practice_tests
from scripts.mac_practice_export import _udemy_cookie_count, run
from scripts.mac_practice_companion import APP_ORIGINS, TOKEN, allowed_origin, valid_pairing


URL = (
    "https://www.udemy.com/course/anthropic-claude-certified-architect-"
    "3-full-practice-exams/learn/quiz/7570481#overview"
)


def fake_udemy_jar():
    jar = CookieJar()
    jar.set_cookie(create_cookie(name="synthetic_session", value="fake-test-only",
                                 domain=".udemy.com", path="/"))
    return jar


class MacPracticeExportTests(unittest.TestCase):
    def test_companion_requires_exact_local_origin_and_pairing_token(self):
        origin = sorted(APP_ORIGINS)[0]
        self.assertTrue(allowed_origin(origin))
        self.assertFalse(allowed_origin("https://attacker.example"))
        self.assertTrue(valid_pairing(origin, TOKEN))
        self.assertFalse(valid_pairing(origin, "wrong-token"))
        self.assertFalse(valid_pairing("https://attacker.example", TOKEN))

    def test_session_uses_in_memory_browser_jar(self):
        jar = fake_udemy_jar()
        session = _session_from_cookiejar(jar, URL)
        try:
            self.assertIs(session.cookies, jar)
            self.assertEqual(_udemy_cookie_count(jar), 1)
        finally:
            session.close()

    def test_local_export_never_writes_cookie_file_or_uploads(self):
        jar = fake_udemy_jar()
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            result = SimpleNamespace(
                item_count=1,
                assessment_count=121,
                output_html=out / "diagnostic.html",
                output_pdf=out / "practice.pdf",
                output_set_pdfs=[],
                output_json=out / "practice.json",
                output_markdown=out / "practice.md",
                output_verification_report=out / "verification.md",
                warnings=[],
            )
            with (
                patch("scripts.mac_practice_export.extract_cookies_from_browser", return_value=jar) as browser,
                patch("scripts.mac_practice_export.export_practice_tests", return_value=result) as exporter,
            ):
                code = run([URL, "--downloads-dir", str(out), "--browser", "chrome"])
            self.assertEqual(code, 0)
            browser.assert_called_once_with("chrome")
            exporter.assert_called_once()
            args, kwargs = exporter.call_args
            self.assertEqual(args[0], URL.split("#", 1)[0])
            self.assertIsNone(args[1])
            self.assertIn("_practice-tests", str(args[2]))
            self.assertIsNotNone(kwargs["session"])
            self.assertEqual(list(out.rglob("*cookies*.txt")), [])

    def test_no_browser_site_session_does_not_attempt_export(self):
        with tempfile.TemporaryDirectory() as temp:
            with (
                patch("scripts.mac_practice_export.extract_cookies_from_browser", return_value=CookieJar()),
                patch("scripts.mac_practice_export.export_practice_tests") as exporter,
            ):
                code = run([URL, "--downloads-dir", temp])
            self.assertEqual(code, 2)
            exporter.assert_not_called()

    def test_zero_questions_does_not_claim_success(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            result = SimpleNamespace(
                item_count=1, assessment_count=0,
                output_html=out / "diagnostic.html", output_pdf=out / "diagnostic.pdf",
                warnings=["assessment endpoint rejected with HTTP 403"],
            )
            with (
                patch("scripts.mac_practice_export.extract_cookies_from_browser", return_value=fake_udemy_jar()),
                patch("scripts.mac_practice_export.export_practice_tests", return_value=result),
            ):
                code = run([URL, "--downloads-dir", temp])
            self.assertEqual(code, 1)

    def test_injected_session_does_not_read_cookie_file(self):
        session = MagicMock()
        with tempfile.TemporaryDirectory() as temp:
            with (
                patch("app.practice_tests._build_session",
                      side_effect=AssertionError("should never load cookie file")),
                patch("app.practice_tests._discover_course", return_value=(None, None, ["no course id"])),
                patch("app.practice_tests._fetch_assessments", return_value=([{"prompt": "Synthetic Q"}], [])),
            ):
                result = export_practice_tests(URL, None, Path(temp), session=session)
            self.assertEqual(result.assessment_count, 1)


if __name__ == "__main__":
    unittest.main()
