"""Video-to-learning POC unit tests (no external media or credentials)."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from app.video_learning import export_learning_package, transcript_quality

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "video_to_learning_poc.py"
spec = importlib.util.spec_from_file_location("video_to_learning_poc", SCRIPT)
poc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(poc)


class VideoToLearningPOCTests(unittest.TestCase):
    def test_supplied_video_url_is_single_video_scoped(self):
        canonical, identity = poc.normalize_youtube_url(
            "https://www.youtube.com/watch?v=fYgggzLEIFs&list=PLL_i-2mmiz0c"
        )
        self.assertEqual(canonical, "https://www.youtube.com/watch?v=fYgggzLEIFs")
        self.assertEqual(identity, "fYgggzLEIFs")
        for bad in (
            "http://www.youtube.com/watch?v=fYgggzLEIFs",
            "https://evil.com/watch?v=fYgggzLEIFs",
            "https://www.youtube.com/playlist?list=PLL_i-2mmiz0c",
        ):
            with self.assertRaises(ValueError):
                poc.normalize_youtube_url(bad)

    def test_coverage_does_not_double_count_overlaps(self):
        transcript = {"segments": [
            {"start_ms": 0, "end_ms": 10000, "text": "Introduction to data"},
            {"start_ms": 9000, "end_ms": 20000, "text": "Now the next section"},
            {"start_ms": 55000, "end_ms": 60000, "text": "Closing the topic"},
        ]}
        report = transcript_quality(transcript, 60000)
        self.assertEqual(report.caption_coverage_ratio, round(25000 / 60000, 4))
        self.assertEqual(report.gap_count_over_30s, 1)
        self.assertEqual(report.visual_analysis, "not_performed")
        self.assertEqual(report.status, "transcribed_unverified")

    def test_empty_or_bad_timestamps_never_pass(self):
        self.assertEqual(transcript_quality({"segments": []}, 5000).status, "needs_review")
        result = transcript_quality({
            "segments": [{"start_ms": 900, "end_ms": 800, "text": "bad cue"}]
        }, 1000)
        self.assertEqual(result.invalid_timing_segments, 1)
        self.assertEqual(result.status, "needs_review")

    def test_real_artifact_export_from_synthetic_vtt(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "demo.en.vtt"
            file.write_text(
                "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nPython reads rows."
                "\n\n00:00:04.000 --> 00:00:06.000\nSQL joins tables.\n",
                encoding="utf-8",
            )
            result = export_learning_package(
                file, title="Synthetic verification",
                source_url="https://www.youtube.com/watch?v=fYgggzLEIFs",
                duration_ms=8000,
            )
            self.assertEqual(result["quality"]["word_count"], 6)
            self.assertEqual(result["quality"]["caption_coverage_ratio"], 0.5)
            guide = Path(result["artifacts"]["study_guide"]).read_text(encoding="utf-8")
            self.assertIn("Python reads rows.", guide)
            self.assertIn("SQL joins tables.", guide)
            self.assertIn("not a verified", guide.lower())
            self.assertTrue(Path(result["artifacts"]["srt"]).exists())
            self.assertTrue(Path(result["artifacts"]["vtt"]).exists())
            self.assertTrue(Path(result["artifacts"]["quality_report"]).exists())
            self.assertTrue(Path(result["artifacts"]["study_guide"]).parent.name.startswith("."))
            self.assertEqual(json.loads(Path(result["artifacts"]["quality_report"]).read_text())["visual_analysis"], "not_performed")

    def test_plain_text_does_not_claim_timestamps(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "lesson.txt"
            path.write_text("A local authorized transcript.", encoding="utf-8")
            result = export_learning_package(path, title="Plain", source_url="", duration_ms=5000)
            self.assertEqual(result["quality"]["status"], "needs_review")
            self.assertNotIn("srt", result["artifacts"])
            self.assertNotIn("vtt", result["artifacts"])


if __name__ == "__main__":
    unittest.main()
