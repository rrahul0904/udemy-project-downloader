import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


class CourseIntelligenceOSUITests(unittest.TestCase):
    def read(self, name: str) -> str:
        return (STATIC / name).read_text(encoding="utf-8")

    def test_new_navigation_routes_and_surfaces_exist(self):
        main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        for route, file_name in (
            ('@app.get("/home")', "home.html"),
            ('@app.get("/library")', "home.html"),
            ('@app.get("/files-ui")', "files.html"),
            ('@app.get("/settings")', "settings.html"),
        ):
            self.assertIn(route, main)
            self.assertTrue((STATIC / file_name).is_file())

        for page in ("home.html", "index.html", "learn.html", "viewer.html", "lab.html", "files.html", "settings.html"):
            html = self.read(page)
            self.assertIn("Course Intelligence OS", html, page)
            self.assertIn('href="/home"', html, page)
            self.assertIn('href="/learn"', html, page)
            self.assertIn('href="/lab"', html, page)

    def test_authorization_privacy_and_data_honesty_copy_are_preserved(self):
        acquire = self.read("index.html")
        learn = self.read("learn.html")
        viewer = self.read("viewer.html")
        settings = self.read("settings.html")
        self.assertIn("I am authorized to archive this content for local personal use.", acquire)
        self.assertIn("Use only authorized material", acquire)
        self.assertIn("does not provide DRM or access-control bypass", acquire)
        self.assertIn("Cookie contents are not displayed in job logs", acquire)
        self.assertIn("Generated study material will never overwrite your personal notes", learn)
        self.assertIn("COURSE_GROUNDED", learn)
        self.assertIn("Transcript-only mode", viewer)
        self.assertIn("reports status instead of inventing a writable browser setting", settings)

    def test_learn_surface_contains_complete_grounded_workspace_tabs(self):
        learn = self.read("learn.html")
        for tab in (
            "Overview", "Transcript", "AI Notes", "Flashcards", "Quiz", "Concept Map",
            "Ask Course", "My Notes", "Bookmarks", "Files",
        ):
            self.assertIn(f">{tab}<", learn)
        study = self.read("learn-study.js")
        self.assertIn("/api/v1/lessons/", study)
        self.assertIn("/api/v1/chat", study)
        self.assertIn("source-citation", study)
        self.assertIn("Review scheduling is not enabled yet", study)

    def test_study_lab_keeps_all_21_tools_and_adds_filters(self):
        lab = self.read("lab.html")
        tool_ids = re.findall(r'data-tool="([^"]+)"', lab)
        self.assertEqual(len(tool_ids), 21)
        self.assertEqual(len(set(tool_ids)), 21)
        expected = {
            "statistics", "cleaner", "outliers", "curve", "errorbars", "plot", "digitizer",
            "xvg", "structure", "coordinates", "workflow", "bibtex", "bibdedupe", "doi",
            "journal", "latextable", "equation", "units", "pomodoro", "decision", "kinetics",
        }
        self.assertEqual(set(tool_ids), expected)
        for category in ("all", "data", "molecular", "writing", "units", "study"):
            self.assertIn(f'data-filter="{category}"', lab)
        self.assertIn("load-course-file", lab)
        self.assertIn("course-file", lab)
        self.assertIn("RECENT_KEY", self.read("lab-ui.js"))

    def test_theme_accessibility_and_responsive_contract_are_present(self):
        css = self.read("os.css")
        for token in (
            "--background: #f6f3ec", "--course-blue: #2563eb", "--knowledge-violet: #7c3aed",
            "--study-green: #15803d", "--lab-orange: #d97706", "--source-cyan: #0891b2",
        ):
            self.assertIn(token, css.lower())
        self.assertIn('html[data-theme="dark"]', css)
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn(":focus-visible", css)
        self.assertIn("@media (max-width: 720px)", css)
        viewer = self.read("viewer.html")
        self.assertIn("Space · play/pause", viewer)
        self.assertIn("J/K · jump -/+10s", viewer)
        self.assertIn('aria-label="Synchronized transcript"', viewer)

    def test_all_new_frontend_modules_are_in_canonical_syntax_gate(self):
        verify = (ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8")
        self.assertIn("for asset in app/static/*.js", verify)
        for file_name in (
            "os.js", "home.js", "files.js", "settings.js", "acquire-ui.js", "learn-study.js", "lab-ui.js"
        ):
            self.assertTrue((STATIC / file_name).is_file(), file_name)


if __name__ == "__main__":
    unittest.main()
