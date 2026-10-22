"""Integrity checks for the 69-course local Claude extraction workflow."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.claude_certification_batch import MANIFEST, ROOT, initial_record, inspect_export, load_manifest
from scripts.claude_question_bank import identity, question_records, resolve_correct
from app.practice_tests import _assessment_explanation


class ClaudeCertificationBatchTests(unittest.TestCase):
    def test_manifest_keeps_all_six_groups_and_69_unique_slugs(self):
        manifest, courses, digest = load_manifest(MANIFEST)
        self.assertEqual(len(courses), 69)
        self.assertEqual(len(set(c["slug"] for c in courses)), 69)
        self.assertEqual(manifest["summary"]["duplicate_occurrences_removed"], 14)
        self.assertEqual(len(digest), 64)

    def test_fingerprint_ignores_option_order_but_not_changed_options(self):
        first, stem = identity("  What is Claude? ", ["Model", "Tool"])
        second, same_stem = identity("what is CLAUDE?", ["Tool", "Model"])
        different, same_stem_again = identity("What is Claude?", ["Model", "Browser"])
        self.assertEqual(first, second)
        self.assertNotEqual(first, different)
        self.assertEqual(stem, same_stem)
        self.assertEqual(stem, same_stem_again)

    def test_answer_key_links_to_source_option_order(self):
        self.assertEqual(resolve_correct(["b"], ["First", "Second"]), ["Second"])
        self.assertEqual(resolve_correct(["Second"], ["First", "Second"]), ["Second"])
        self.assertIsNone(resolve_correct(["c"], ["First", "Second"]))

    def test_plural_feedback_uses_only_returned_correct_option(self):
        question = {"prompt": {"question": "Synthetic question", "answers": ["A", "B"],
                               "feedbacks": ["Wrong explanation", "Correct explanation"]},
                    "correct_response": ["b"]}
        self.assertEqual(_assessment_explanation(question), "Correct explanation")
        question["correct_response"] = ["c"]
        self.assertEqual(_assessment_explanation(question), "")

    def test_zero_question_diagnostic_never_becomes_complete(self):
        course = load_manifest(MANIFEST)[1][0]
        with tempfile.TemporaryDirectory(dir=ROOT / "downloads") as temp:
            directory = Path(temp)
            path = directory / "synthetic-practice-tests.json"
            payload = {
                "course_url": course["url"], "course_id": "123", "course_title": "Synthetic",
                "exported_at": "2026-10-22T00:00:00Z", "practice_tests": [],
                "validation": {"status": "no_practice_tests", "practice_sets_discovered": 0,
                               "questions_retrieved": 0, "questions_expected": 0},
                "warnings": [],
            }
            path.write_text(json.dumps(payload))
            for suffix in ("pdf", "html", "md"):
                path.with_suffix("." + suffix).write_bytes(b"synthetic-content" * 20)
            path.with_name(path.stem + "-verification-report.md").write_bytes(b"synthetic-content" * 20)
            record = inspect_export(path, course)
            self.assertEqual(record["export_state"], "no_quizzes")
            self.assertEqual(record["extracted_question_count"], 0)

    def test_cross_quiz_duplicates_keep_both_source_instances(self):
        course = load_manifest(MANIFEST)[1][0]
        with tempfile.TemporaryDirectory(dir=ROOT / "downloads") as temp:
            directory = Path(temp)
            path = directory / "synthetic-practice-tests.json"
            assessment = {"id": 91, "prompt": {"question": "Synthetic stem", "answers": ["A", "B"]},
                          "correct_response": "A", "explanation": "Synthetic explanation"}
            data = {"course_id": "123", "practice_tests": [
                {"id": 11, "title": "Set 1", "assessments": [assessment]},
                {"id": 22, "title": "Set 2", "assessments": [assessment]},
            ]}
            path.write_text(json.dumps(data))
            import hashlib
            record = initial_record(course)
            record.update(actual_title="Synthetic", course_id="123", extracted_question_count=2,
                          output_paths={"json": str(path.relative_to(ROOT))},
                          json_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            questions, courses, exams, duplicates = question_records(course["certification_code"], [record])
            self.assertEqual(len(questions), 1)
            self.assertEqual(len(questions[0]["sources"]), 2)
            self.assertEqual(questions[0]["answer_variants"][0]["resolved_correct_options"], ["A"])
            self.assertEqual({s["quiz_id"] for s in questions[0]["sources"]}, {"11", "22"})
            self.assertEqual(len(exams), 2)
            self.assertEqual(len(duplicates), 1)


if __name__ == "__main__":
    unittest.main()
