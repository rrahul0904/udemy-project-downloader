import base64
import json
import re
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from app.practice_tests import (
    _assessment_answers,
    _assessment_explanation,
    _assessment_prompt,
    _friendly_course_prefix,
    _friendly_test_title,
    _item_expected_count,
    _item_version,
    _slugify_file_stem,
    _to_markdown,
    _to_pdf,
    _validation_summary,
    _deduplicate_assessments,
    _fetch_paginated,
    _fetch_curriculum,
    _fetch_assessments,
    _publish_staged_files,
    export_practice_tests,
)


class PracticeTestFormattingTests(unittest.TestCase):
    @staticmethod
    def _pdf_content_streams(path: Path) -> bytes:
        content = path.read_bytes()
        decoded = []
        for match in re.finditer(rb"stream\r?\n(.*?)endstream", content, re.DOTALL):
            stream = match.group(1)
            try:
                decoded.append(zlib.decompress(base64.a85decode(stream.removesuffix(b"~>"))))
            except (ValueError, zlib.error):
                continue
        return b"\n".join(decoded)

    def test_nested_udemy_prompt_is_rendered_cleanly(self):
        assessment = {
            "prompt": {
                "question": "What is Snowflake?",
                "answers": ["A cloud data platform", "A spreadsheet"],
                "explanation": "Snowflake is a cloud data platform.",
            },
            "correct_response": ["a"],
        }

        self.assertEqual(_assessment_prompt(assessment), "What is Snowflake?")
        self.assertEqual(_assessment_answers(assessment), ["A cloud data platform", "A spreadsheet"])
        self.assertEqual(_assessment_explanation(assessment), "Snowflake is a cloud data platform.")

        payload = {
            "course_title": "Snowflake Test Course",
            "course_id": "123",
            "course_url": "https://www.udemy.com/course/example/",
            "exported_at": "2026-08-13T00:00:00+00:00",
            "practice_tests": [
                {
                    "title": "Practice Exam 1",
                    "assessments": [assessment],
                }
            ],
            "warnings": [],
        }
        markdown = _to_markdown(payload)

        self.assertIn("### 1. What is Snowflake?", markdown)
        self.assertIn("- A. A cloud data platform", markdown)
        self.assertIn("Correct response: `A`", markdown)
        self.assertNotIn('{"answers"', markdown)

    def test_curriculum_metadata_helpers_read_nested_quiz_fields(self):
        item = {
            "quiz": {
                "version": "55",
                "num_assessments": "121",
            }
        }

        self.assertEqual(_item_version(item), 55)
        self.assertEqual(_item_expected_count(item), 121)

    def test_friendly_set_name_from_course_title(self):
        prefix = _friendly_course_prefix(
            "5 Practice Exams COF-C02 Snowflake Core Certification",
            "https://www.udemy.com/course/5-practice-exams-cof-c02-snowflake-core-certification/learn/quiz/6868763",
        )

        self.assertEqual(prefix, "Snowflake Core Certification")
        self.assertEqual(_friendly_test_title(prefix, "Practice Exam 1", 1), "Snowflake Core Certification Set 1")
        self.assertEqual(_slugify_file_stem("Snowflake Core Certification Set 1"), "snowflake-core-certification-set-1")
        self.assertEqual(
            _friendly_course_prefix(
                None,
                "https://www.udemy.com/course/5-practice-exams-cof-c02-snowflake-core-certification/learn/quiz/6868763",
            ),
            "Snowflake Core Certification",
        )

    def test_category_neutral_set_titles_and_question_formatting(self):
        for category in ("AWS", "Snowflake", "Databricks", "Claude"):
            with self.subTest(category=category):
                prefix = _friendly_course_prefix(
                    f"{category} Practice Tests", "https://www.udemy.com/course/synthetic/"
                )
                self.assertEqual(prefix, category)
                title = _friendly_test_title(prefix, "Practice Test 1", 1)
                self.assertEqual(title, f"{category} Set 1")
                markdown = _to_markdown({
                    "course_title": f"{category} Practice Tests", "course_id": "123",
                    "exported_at": "2026-01-01T00:00:00Z", "warnings": [],
                    "practice_tests": [{"title": title, "assessments": [{
                        "prompt": {"question": "Synthetic question?", "answers": ["A", "B"]}
                    }]}],
                })
                self.assertIn("Synthetic question?", markdown)
                self.assertIn(title, markdown)

    def test_pdf_export_writes_file(self):
        payload = {
            "course_title": "Snowflake Test Course",
            "course_id": "123",
            "course_url": "https://www.udemy.com/course/example/",
            "exported_at": "2026-08-13T00:00:00+00:00",
            "practice_tests": [
                {
                    "title": "Practice Exam 1",
                    "assessments": [
                        {
                            "prompt": {
                                "question": "What is Snowflake?",
                                "answers": ["A cloud data platform", "A spreadsheet"],
                            },
                            "correct_response": ["a"],
                        }
                    ],
                }
            ],
            "warnings": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "practice-tests.pdf"
            _to_pdf(json.loads(json.dumps(payload)), output_path)

            self.assertTrue(output_path.is_file())
            self.assertGreater(output_path.stat().st_size, 1000)

    def test_validation_detects_missing_questions_and_answers(self):
        tests = [{
            "expected_assessment_count": 3,
            "assessments": [{
                "prompt": {"question": "Synthetic question?", "answers": [
                    {"text": "First", "is_correct": True}, {"text": "Second"}
                ], "explanation": "Synthetic explanation"},
            }],
        }]
        summary = _validation_summary("123", tests, [])
        self.assertEqual(summary["status"], "partial")
        self.assertEqual(summary["count_reconciliation"], "PARTIAL")
        self.assertEqual(summary["questions_expected"], 3)
        self.assertEqual(summary["questions_retrieved"], 1)
        self.assertEqual(summary["questions_with_answer_choices"], 1)
        self.assertEqual(summary["questions_with_correct_answers"], 1)
        self.assertEqual(summary["questions_with_explanations"], 1)

    def test_validation_never_succeeds_with_zero_questions_or_unknown_count(self):
        self.assertEqual(_validation_summary("123", [], [])["status"], "no_practice_tests")
        self.assertEqual(
            _validation_summary("123", [{"expected_assessment_count": 2, "assessments": []}], [])["status"],
            "failed",
        )
        self.assertEqual(
            _validation_summary("123", [{"assessments": [{"prompt": "Synthetic?"}]}], [])["status"],
            "partial",
        )
        self.assertEqual(
            _validation_summary(None, [], ["Course page returned HTTP 403."])["status"],
            "not_accessible",
        )

    def test_omitted_question_text_is_partial_even_when_retained_count_matches(self):
        summary = _validation_summary(
            "123",
            [{"expected_assessment_count": 1, "assessments": [{
                "prompt": {"question": "Synthetic question?", "answers": ["A", "B"]}
            }]}],
            ["Omitted 1 assessment record(s) without question text from Synthetic Set."],
        )
        self.assertEqual(summary["questions_expected"], 1)
        self.assertEqual(summary["questions_retrieved"], 1)
        self.assertEqual(summary["count_reconciliation"], "PASS")
        self.assertEqual(summary["status"], "partial")

    def test_duplicate_ids_removed_without_collapsing_idless_questions(self):
        items = [{"id": 1}, {"id": 1}, {"prompt": "same"}, {"prompt": "same"}]
        unique, removed = _deduplicate_assessments(items)
        self.assertEqual(removed, 1)
        self.assertEqual(len(unique), 3)

    def test_pagination_collects_all_pages_and_rejects_foreign_next_url(self):
        class Response:
            status_code = 200

            def __init__(self, data):
                self.data = data

            def json(self):
                return self.data

        class Session:
            def __init__(self, pages):
                self.pages = pages
                self.calls = []

            def get(self, url, **kwargs):
                self.calls.append(url)
                return Response(self.pages.pop(0))

        endpoint = "https://www.udemy.com/api-2.0/quizzes/7/assessments/"
        session = Session([
            {"results": [{"id": 1}], "next": "?page=2"},
            {"results": [{"id": 2}], "next": None},
        ])
        items, warnings = _fetch_paginated(session, endpoint, {"page_size": "1"}, "assessments")
        self.assertEqual([item["id"] for item in items], [1, 2])
        self.assertEqual(warnings, [])
        self.assertEqual(len(session.calls), 2)

        session = Session([{"results": [{"id": 1}], "next": "https://other.example/page"}])
        items, warnings = _fetch_paginated(session, endpoint, None, "assessments")
        self.assertEqual(len(items), 1)
        self.assertEqual(len(session.calls), 1)
        self.assertIn("another origin", warnings[0])

    def test_authenticated_endpoint_rejection_is_reported(self):
        class Response:
            status_code = 403

        class Session:
            def get(self, url, **kwargs):
                return Response()

        items, warnings = _fetch_paginated(
            Session(), "https://www.udemy.com/api-2.0/quizzes/7/assessments/", None, "assessments"
        )
        self.assertEqual(items, [])
        self.assertIn("HTTP 403", warnings[0])

    def test_clean_empty_fallback_does_not_hide_auth_rejection(self):
        for fetcher, args in (
            (_fetch_curriculum, (object(), "https://www.udemy.com/course/synthetic/", "123")),
            (_fetch_assessments, (object(), "https://www.udemy.com/course/synthetic/", "7")),
        ):
            with self.subTest(fetcher=fetcher.__name__):
                with patch("app.practice_tests._fetch_paginated", side_effect=[
                    ([], ["endpoint rejected the authenticated request with HTTP 403."]),
                    ([], []),
                ]):
                    items, warnings = fetcher(*args)
                self.assertEqual(items, [])
                self.assertTrue(any("HTTP 403" in warning for warning in warnings))

    def test_pdf_failure_does_not_write_json_claiming_success(self):
        item = {"id": 7, "_class": "practice", "title": "Practice Test 1", "num_assessments": 1}
        question = {"id": 99, "prompt": {"question": "Synthetic question?", "answers": ["A", "B"]}}
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.practice_tests._build_session", return_value=object()), \
                 patch("app.practice_tests._discover_course", return_value=("123", "Synthetic Course", [])), \
                 patch("app.practice_tests._fetch_curriculum", return_value=([item], [])), \
                 patch("app.practice_tests._fetch_assessments", return_value=([question], [])), \
                 patch("app.practice_tests._to_pdf", side_effect=OSError("synthetic PDF failure")):
                with self.assertRaises(OSError):
                    export_practice_tests(
                        "https://www.udemy.com/course/synthetic/", Path("unused"), Path(tmpdir)
                    )
            self.assertEqual(list(Path(tmpdir).glob("*.json")), [])
            self.assertEqual(list(Path(tmpdir).glob(".practice-stage-*")), [])

    def test_publish_failure_restores_prior_exports(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            stage_dir = output_dir / ".stage"
            stage_dir.mkdir()
            existing = output_dir / "first.txt"
            existing.write_text("original", encoding="utf-8")
            staged_first = stage_dir / "first.txt"
            staged_first.write_text("replacement", encoding="utf-8")
            staged_second = stage_dir / "second.txt"
            staged_second.write_text("new", encoding="utf-8")
            original_replace = Path.replace

            def fail_second(path, target):
                if path == staged_second:
                    raise OSError("synthetic publish failure")
                return original_replace(path, target)

            with patch.object(Path, "replace", fail_second):
                with self.assertRaises(OSError):
                    _publish_staged_files([staged_first, staged_second], output_dir, stage_dir)
            self.assertEqual(existing.read_text(encoding="utf-8"), "original")
            self.assertFalse((output_dir / "second.txt").exists())

    def test_export_writes_validation_to_json_and_set_pdf(self):
        item = {"id": 7, "_class": "practice", "title": "Practice Test 1", "num_assessments": 2}
        question = {"id": 99, "prompt": {"question": "Synthetic question?", "answers": ["A", "B"]}}
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("app.practice_tests._build_session", return_value=object()), \
                 patch("app.practice_tests._discover_course", return_value=("123", "Synthetic Course", [])), \
                 patch("app.practice_tests._fetch_curriculum", return_value=([item], [])), \
                 patch("app.practice_tests._fetch_assessments", return_value=([question, {"id": 100}], [])):
                result = export_practice_tests("https://www.udemy.com/course/synthetic/", Path("unused"), Path(tmpdir))
            self.assertEqual(result.validation["status"], "partial")
            self.assertEqual(result.validation["questions_expected"], 2)
            self.assertEqual(result.assessment_count, 1)
            self.assertTrue(any("without question text" in warning for warning in result.warnings))
            self.assertEqual(len(result.output_set_pdfs), 1)
            self.assertTrue(result.output_verification_report.is_file())
            report = result.output_verification_report.read_text(encoding="utf-8")
            self.assertIn("1 retrieved / 2 expected", report)
            self.assertIn("Count reconciliation: PARTIAL", report)
            payload = json.loads(result.output_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["validation"], result.validation)
            self.assertTrue(all(payload["validation"][key] for key in (
                "json_generated", "html_generated", "markdown_generated", "pdf_generated",
                "verification_report_generated"
            )))
            markdown = result.output_markdown.read_text(encoding="utf-8")
            html = result.output_html.read_text(encoding="utf-8")
            pdf_streams = self._pdf_content_streams(result.output_pdf)
            for label in ("JSON", "HTML", "Markdown", "PDF"):
                self.assertIn(f"{label} generated: YES", markdown)
                self.assertIn(f"{label} generated", html)
                self.assertIn(b"YES", pdf_streams)
                self.assertIn(f"{label} generated: YES".encode(), pdf_streams)
            self.assertEqual(list(Path(tmpdir).glob(".practice-stage-*")), [])


if __name__ == "__main__":
    unittest.main()
