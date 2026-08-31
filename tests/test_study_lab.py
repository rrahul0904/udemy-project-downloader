import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StudyLabIntegrationTests(unittest.TestCase):
    def test_study_lab_assets_exist(self):
        for relative in (
            "app/static/lab.html",
            "app/static/lab.css",
            "app/static/lab.js",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_fastapi_exposes_study_lab_route(self):
        main = (ROOT / "app/main.py").read_text(encoding="utf-8")
        self.assertIn('@app.get("/lab")', main)
        self.assertIn('STATIC_DIR / "lab.html"', main)

    def test_downloader_links_to_study_lab(self):
        index = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
        self.assertIn('href="/lab"', index)
        self.assertIn("Study Lab", index)

    def test_lab_uses_existing_download_inventory_and_guarded_file_route(self):
        script = (ROOT / "app/static/lab.js").read_text(encoding="utf-8")
        self.assertIn("fetch('/api/downloads')", script)
        self.assertIn("/files/${encodedFilePath(path)}", script)

    def test_lab_contains_reference_tool_categories(self):
        html = (ROOT / "app/static/lab.html").read_text(encoding="utf-8")
        for label in (
            "Statistics Calculator",
            "Plot Digitizer",
            "XVG Visualizer",
            "Structure Inspector",
            "BibTeX Sanitizer",
            "DOI → BibTeX",
            "Scientific Converter",
            "Pomodoro Timer",
        ):
            self.assertIn(label, html)

    def test_study_lab_documentation_records_parity_scope(self):
        docs = (ROOT / "docs/STUDY_LAB.md").read_text(encoding="utf-8")
        self.assertIn("functional integrated MVP", docs)
        self.assertIn("https://github.com/LD-Shell/stemkit", docs)
        self.assertIn("License: MIT", docs)


if __name__ == "__main__":
    unittest.main()
