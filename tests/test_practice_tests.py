import json
import tempfile
import unittest
from pathlib import Path

from app.practice_tests import (
    _assessment_answers,
    _assessment_explanation,
    _assessment_prompt,
    _item_expected_count,
    _item_version,
    _to_markdown,
    _to_pdf,
)


class PracticeTestFormattingTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
