import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs" / "parity-matrix.json"
ALLOWED = {
    "EXACT",
    "FUNCTIONAL_EQUIVALENT",
    "PARTIAL",
    "MISSING",
    "INTENTIONALLY_EXCLUDED",
    "NOT_APPLICABLE",
}


class ParityMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(MATRIX.read_text(encoding="utf-8"))
        cls.items = cls.payload["capabilities"]

    def test_matrix_is_substantive_and_uses_known_statuses(self):
        self.assertGreaterEqual(len(self.items), 25)
        self.assertEqual(set(self.payload["statuses"]), ALLOWED)

    def test_every_capability_has_traceability_fields(self):
        required = {
            "reference",
            "area",
            "feature",
            "status",
            "implementation",
            "tests",
            "notes",
            "priority",
            "tracking",
        }
        for item in self.items:
            with self.subTest(feature=item.get("feature")):
                self.assertTrue(required.issubset(item))
                self.assertIn(item["status"], ALLOWED)
                self.assertIn(item["priority"], {"P0", "P1", "P2", "P3"})
                self.assertTrue(item["reference"].strip())
                self.assertTrue(item["area"].strip())
                self.assertTrue(item["feature"].strip())
                self.assertTrue(item["notes"].strip())
                self.assertTrue(item["tracking"].strip())

    def test_parity_claims_have_code_and_test_evidence(self):
        for item in self.items:
            if item["status"] not in {"EXACT", "FUNCTIONAL_EQUIVALENT"}:
                continue
            with self.subTest(feature=item["feature"]):
                self.assertTrue(item["implementation"], "Parity claim requires implementation evidence")
                self.assertTrue(item["tests"], "Parity claim requires test evidence")
                for relative in item["implementation"] + item["tests"]:
                    self.assertTrue((ROOT / relative).exists(), relative)

    def test_missing_capabilities_have_an_explicit_plan(self):
        for item in self.items:
            if item["status"] != "MISSING":
                continue
            with self.subTest(feature=item["feature"]):
                self.assertTrue(item["tracking"].startswith(("issue:", "parity-")))
                self.assertIn(item["priority"], {"P0", "P1", "P2", "P3"})

    def test_intentionally_excluded_items_explain_the_decision(self):
        excluded = [item for item in self.items if item["status"] == "INTENTIONALLY_EXCLUDED"]
        self.assertTrue(excluded)
        for item in excluded:
            self.assertGreaterEqual(len(item["notes"]), 20)


if __name__ == "__main__":
    unittest.main()
