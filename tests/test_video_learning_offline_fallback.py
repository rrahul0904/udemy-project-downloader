"""Offline downloaded-media fallback tests for the real HTTP 429 failure."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yt_dlp.utils import DownloadError

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "video_to_learning_poc.py"
spec = importlib.util.spec_from_file_location("video_to_learning_poc_offline", SCRIPT)
poc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(poc)

URL = "https://www.youtube.com/watch?v=fYgggzLEIFs"


class OfflineFallbackTests(unittest.TestCase):
    def test_detects_downloaded_youtube_video_with_original_title(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "My Course"
            folder.mkdir()
            path = folder / "Snowflake CoCo [fYgggzLEIFs].mp4"
            path.write_bytes(b"synthetic media only")
            self.assertEqual(poc.find_downloaded_media(root, "fYgggzLEIFs"), path)
            self.assertIsNone(poc.find_downloaded_media(root, "ooooooooooo"))
            info_path = folder / "Snowflake CoCo [fYgggzLEIFs].info.json"
            info_path.write_text(json.dumps({
                "id": "fYgggzLEIFs", "title": "Snowflake CoCo", "duration": 844,
            }), encoding="utf-8")
            self.assertEqual(poc.downloaded_video_info(path, "fYgggzLEIFs")["duration"], 844)

    def test_local_caption_preferred_without_any_youtube_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "Course"
            folder.mkdir()
            caption = folder / "Snowflake CoCo [fYgggzLEIFs].en.vtt"
            caption.write_text(
                "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nSnowflake cost metrics.",
                encoding="utf-8",
            )
            media = folder / "Snowflake CoCo [fYgggzLEIFs].mp4"
            media.write_bytes(b"synthetic media only")
            with patch.object(poc, "download_caption", side_effect=AssertionError("network not allowed")), patch(
                "app.visual_learning._duration_seconds", return_value=844.0
            ):
                rc = poc.main(["--url", URL, "--download-root", str(root),
                               "--data-root", str(root / "db"), "--no-index"])
            self.assertEqual(rc, 0)
            self.assertTrue((folder / ".Snowflake CoCo [fYgggzLEIFs].en.learning" / "quality-report.json").exists())

    def test_already_downloaded_video_uses_local_whisper_not_youtube(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "Course"
            folder.mkdir()
            media = folder / "Snowflake CoCo [fYgggzLEIFs].mp4"
            media.write_bytes(b"synthetic media only")
            with patch.object(poc, "download_caption", side_effect=AssertionError("network not allowed")), patch.object(
                poc, "transcribe_with_local_whisper",
                return_value=[{"start_ms": 1000, "end_ms": 3000, "text": "HTML reports from Snowflake"}]
            ), patch("app.visual_learning._duration_seconds", return_value=844.0):
                rc = poc.main(["--url", URL, "--download-root", str(root),
                               "--asr-fallback", "--no-index"])
            self.assertEqual(rc, 0)
            self.assertTrue((folder / "Snowflake CoCo [fYgggzLEIFs].en.vtt").exists())
            self.assertTrue((folder / ".Snowflake CoCo [fYgggzLEIFs].en.learning" /
                             "transcript.json").exists())

    def test_local_media_without_asr_prints_actionable_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "lecture [fYgggzLEIFs].mp4").write_bytes(b"synthetic media only")
            with patch.object(poc, "download_caption", side_effect=AssertionError("network not allowed")), patch(
                "builtins.print"
            ) as printed:
                rc = poc.main(["--url", URL, "--download-root", str(root), "--no-index"])
            self.assertEqual(rc, 2)
            obj = json.loads(printed.call_args.args[0])
            self.assertEqual(obj["status"], "blocked")
            self.assertIn("speech recognition", obj["reason"].lower())

    def test_http_429_is_json_block_not_python_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(poc, "download_caption", side_effect=DownloadError(
                "ERROR: Unable to download video subtitles for 'en': HTTP Error 429: Too Many Requests"
            )), patch("builtins.print") as printed:
                rc = poc.main(["--url", URL, "--download-root", directory, "--no-index"])
            self.assertEqual(rc, 2)
            obj = json.loads(printed.call_args.args[0])
            self.assertIn("429", obj["reason"])
            self.assertIn("previously downloaded MP4", obj["reason"])

    def test_worker_is_optional_and_durable(self):
        project_root = Path(__file__).resolve().parents[1]
        compose = (project_root / "docker-compose.yml").read_text(encoding="utf-8")
        docker = (project_root / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn('profiles: ["transcribe"]', compose)
        self.assertIn("INSTALL_LOCAL_ASR: \"1\"", compose)
        self.assertIn("HF_HOME: /app/data/.cache/huggingface", compose)
        self.assertIn("INSTALL_LOCAL_ASR=0", docker)
        self.assertIn("requirements-asr.txt", docker)


if __name__ == "__main__":
    unittest.main()
