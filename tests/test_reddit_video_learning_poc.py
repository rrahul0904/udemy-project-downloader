"""Reddit video ingestion without remote requests or copyrighted fixture media."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "reddit_video_to_learning_poc.py"
spec = importlib.util.spec_from_file_location("reddit_learning_cli", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
URL = "https://www.reddit.com/r/aiagents/s/t94FoWZPvK"


def video():
    return {
        "id": "redditvid123",
        "title": "Synthetic Reddit agent clip",
        "extractor_key": "Reddit",
        "webpage_url": "https://www.reddit.com/r/aiagents/comments/abc123/demo/",
        "duration": 25,
        "formats": [
            {"format_id": "v", "vcodec": "h264", "acodec": "none"},
            {"format_id": "a", "vcodec": "none", "acodec": "aac"},
        ],
    }


class RedditVideoPOCTests(unittest.TestCase):
    def test_share_url_and_canonical_urls_are_allowed(self):
        self.assertEqual(module.validate_reddit_url(URL), URL)
        self.assertEqual(
            module.validate_reddit_url("https://reddit.com/r/aiagents/comments/abc123/video/?utm_source=share"),
            "https://reddit.com/r/aiagents/comments/abc123/video",
        )
        self.assertEqual(module.validate_reddit_url("https://redd.it/abc123"), "https://redd.it/abc123")

    def test_rejects_untrusted_host_and_unsupported_paths(self):
        for src in [
            "http://www.reddit.com/r/aiagents/s/t94FoWZPvK",
            "https://www.reddit.com.evil.example/r/aiagents/s/t94FoWZPvK",
            "https://www.reddit.com/r/aiagents/",
            "https://www.reddit.com/user/test/about",
            "https://user:password@www.reddit.com/r/aiagents/s/t94FoWZPvK",
            "https://www.reddit.com:9999/r/aiagents/s/t94FoWZPvK",
        ]:
            with self.subTest(src=src), self.assertRaises(ValueError):
                module.validate_reddit_url(src)

    def test_good_public_reddit_video_metadata(self):
        obj = module._video_info(video(), URL)
        self.assertEqual(obj["status"], "source_validated")
        self.assertEqual(obj["video_id"], "redditvid123")
        self.assertEqual(obj["formats_available"], 2)
        self.assertTrue(obj["video_stream_verified"])
        self.assertEqual(obj["speech_status"], "not_transcribed")

    def test_text_gallery_and_delegated_media_not_falsely_processed(self):
        for item in [
            {"_type": "playlist", "entries": [video()]},
            {**video(), "extractor_key": "Youtube"},
            {**video(), "formats": [{"vcodec": "none"}], "vcodec": "none"},
            {**video(), "duration": 20000},
        ]:
            with self.subTest(item=item), self.assertRaises(module.IntakeError):
                module._video_info(item, URL)

    def test_metadata_only_never_downloads_and_writes_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(module, "resolve_reddit_video", return_value=(module._video_info(video(), URL), None)) as resolve:
                with patch("builtins.print"):
                    rc = module.main(["--url", URL, "--download-root", str(root), "--metadata-only"])
            self.assertEqual(rc, 0)
            self.assertTrue(resolve.call_args.kwargs["metadata_only"])
            manifest = list(root.rglob("source-intake.json"))
            self.assertEqual(len(manifest), 1)
            self.assertIn("source_validated", manifest[0].read_text(encoding="utf-8"))

    def test_unresolvable_url_exits_blocked_not_fake_transcription(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(module, "resolve_reddit_video", side_effect=module.IntakeError("Unavailable post")), patch("builtins.print") as output:
                status = module.main(["--url", URL, "--download-root", temp, "--metadata-only"])
            self.assertEqual(status, 2)
            self.assertIn('"status": "blocked"', output.call_args.args[0])
            self.assertIn("No learning content was invented", output.call_args.args[0])

    def test_authorized_video_follows_asr_and_ocr_without_youtube(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            video_path = root / "synthetic-reddit-video.mp4"
            video_path.write_bytes(b"synthetic - never actual Reddit media")
            with patch.object(module, "resolve_reddit_video", return_value=(module._video_info(video(), URL), video_path)), patch.object(
                module, "transcribe_with_local_whisper",
                return_value=[{"start_ms": 1000, "end_ms": 3000, "text": "An agent coordinates tools and checks evidence."}],
            ), patch("app.visual_learning._duration_seconds", return_value=25.0), patch(
                "app.visual_learning.analyze_video_visuals",
                return_value={"status": "frames_with_ocr_unverified", "frames_examined": 1},
            ), patch("builtins.print"):
                rc = module.main(["--url", URL, "--download-root", str(root),
                                  "--asr-fallback", "--visuals", "--no-index"])
            self.assertEqual(rc, 0)
            self.assertTrue((root / "synthetic-reddit-video.en.vtt").is_file())
            self.assertEqual(len(list(root.rglob("quality-report.json"))), 1)


if __name__ == "__main__":
    unittest.main()
