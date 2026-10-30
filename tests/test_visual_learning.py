"""Visual-learning tests: deterministic fixtures plus optional local ffmpeg smoke."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import visual_learning as v


class VisualLearningTests(unittest.TestCase):
    def test_candidate_classification_does_not_claim_semantic_verification(self):
        self.assertEqual(v._classify("SELECT id FROM my_table WHERE active = 1"), "code_candidate")
        self.assertEqual(v._classify("def main():\n import re\n return 2"), "code_candidate")
        self.assertEqual(v._classify("System Architecture\nSource -> ETL -> Warehouse"), "diagram_candidate")
        self.assertEqual(v._classify("This slide introduces the five important concepts"), "slide_candidate")
        self.assertEqual(v._classify(""), "unclassified_visual")

    def test_tesseract_tsv_preserves_text_and_confidence(self):
        tsv = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttext\tconf\n"
            "5\t1\t1\t1\t1\t1\t10\tSELECT\t96\n"
            "5\t1\t1\t1\t1\t2\t45\tname\t92\n"
            "5\t1\t1\t1\t2\t1\t10\tFROM\t91\n"
            "5\t1\t1\t1\t2\t2\t45\tusers\t90\n"
            "5\t1\t1\t1\t2\t3\t90\tgarbage\t10\n"
        )
        from subprocess import CompletedProcess
        with patch("app.visual_learning.shutil.which", return_value="/usr/bin/tesseract"), patch(
            "app.visual_learning._exec", return_value=CompletedProcess([], 0, tsv, "")
        ):
            found = v._ocr_image(Path("/fake/frame.jpg"))
        self.assertEqual(found["text"], "SELECT name\nFROM users")
        self.assertEqual(found["line_count"], 2)
        self.assertGreater(found["confidence"], 90)

    def test_manifest_contains_frames_ocr_and_review_flags(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            media = base / "lecture.mp4"
            media.write_bytes(b"synthetic media")
            output = base / "package" / "visuals"
            def frames(_media, folder, duration, limit):
                first, second = folder / "periodic-0001.jpg", folder / "periodic-0002.jpg"
                first.write_bytes(b"fake-jpeg-code")
                second.write_bytes(b"fake-jpeg-diagram")
                return [
                    {"file": first, "time_ms": 0, "selection": "periodic"},
                    {"file": second, "time_ms": 8000, "selection": "periodic"},
                ]
            def fake_ocr(frame):
                text = ("SELECT name FROM customers WHERE active = 1" if "0001" in frame.name
                        else "System Architecture Source -> ETL -> Warehouse")
                return {"status": "completed", "text": text, "confidence": 94.1, "line_count": 2}
            with patch("app.visual_learning.shutil.which", return_value="/fake/command"), patch(
                "app.visual_learning._duration_seconds", return_value=16.0
            ), patch("app.visual_learning._periodic_frames", side_effect=frames), patch(
                "app.visual_learning._scene_frames", return_value=[]
            ), patch("app.visual_learning._ocr_image", side_effect=fake_ocr):
                report = v.analyze_video_visuals(media, output, max_frames=6)
            self.assertEqual(report["status"], "frames_with_ocr_unverified")
            manifest = json.loads(Path(report["manifest"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["frames_examined"], 2)
            self.assertEqual(manifest["items"][0]["category"], "code_candidate")
            self.assertEqual(manifest["items"][1]["category"], "diagram_candidate")
            self.assertIsNone(manifest["items"][0]["vision_description"])
            self.assertEqual(manifest["items"][1]["vision_review"], "not_performed")
            self.assertIn("SELECT name", Path(report["code_candidates"]).read_text(encoding="utf-8"))
            self.assertIn("System Architecture", Path(report["diagram_candidates"]).read_text(encoding="utf-8"))
            self.assertIn("![Frame", Path(report["visual_notes"]).read_text(encoding="utf-8"))

    def test_rejects_wrong_media_or_frame_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            video = base / "lecture.mp4"
            video.write_bytes(b"dummy")
            with self.assertRaises(ValueError):
                v.analyze_video_visuals(base / "missing.mov", base / "out")
            with self.assertRaises(ValueError):
                v.analyze_video_visuals(video, base / "out", max_frames=121)
            with self.assertRaises(ValueError):
                v.analyze_video_visuals(video, base, max_frames=10)

    def test_no_scene_matches_do_not_fail_whole_video(self):
        with tempfile.TemporaryDirectory() as temporary, patch(
            "app.visual_learning._exec",
            side_effect=RuntimeError("ffmpeg: Nothing was written into output file"),
        ):
            found = v._scene_frames(Path("example.mp4"), Path(temporary), 4)
        self.assertEqual(found, [])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg not installed")
    def test_real_ffmpeg_frame_extraction_without_external_video(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            movie = base / "generated.mp4"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=2",
                "-c:v", "mpeg4", str(movie),
            ], check=True, capture_output=True, timeout=40)
            result = v.analyze_video_visuals(movie, base / "visual", max_frames=4)
            self.assertGreaterEqual(result["frames_examined"], 1)
            self.assertTrue(Path(result["manifest"]).exists())
            self.assertIn(result["status"], {"frames_with_ocr_unverified", "frames_only_unverified"})


if __name__ == "__main__":
    unittest.main()
