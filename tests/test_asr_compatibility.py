"""Prevent transcription decoder drift between faster-whisper and PyAV."""
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from app.video_learning import transcribe_with_local_whisper


class ASRCompatibilityTests(unittest.TestCase):
    def test_optional_requirements_pin_known_compatible_pyav(self):
        root = Path(__file__).resolve().parents[1]
        optional = (root / "requirements-asr.txt").read_text(encoding="utf-8")
        dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
        workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("av==18.1.0", optional)
        self.assertIn("python scripts/verify_asr_decoder.py", dockerfile)
        self.assertIn("asr-container-build", workflow)
        self.assertIn("INSTALL_LOCAL_ASR=1", workflow)

    def test_metadata_errors_failure_is_actionable_and_does_not_return_fake_transcript(self):
        with tempfile.TemporaryDirectory() as temp:
            media = Path(temp) / "video.mp4"
            media.write_bytes(b"synthetic")
            class Model:
                def __init__(self, *args, **kwargs):
                    pass

                def transcribe(self, *args, **kwargs):
                    raise TypeError("open() got an unexpected keyword argument 'metadata_errors'")

            fake = types.ModuleType("faster_whisper")
            fake.WhisperModel = Model
            with patch.dict(sys.modules, {"faster_whisper": fake}):
                with self.assertRaisesRegex(RuntimeError, r"av==18\.1\.0"):
                    transcribe_with_local_whisper(media)

    def test_non_compatibility_type_errors_are_not_masked(self):
        with tempfile.TemporaryDirectory() as temp:
            media = Path(temp) / "video.mp4"
            media.write_bytes(b"synthetic")
            class Model:
                def __init__(self, *args, **kwargs):
                    pass

                def transcribe(self, *args, **kwargs):
                    raise TypeError("Unexpected unrelated error")

            fake = types.ModuleType("faster_whisper")
            fake.WhisperModel = Model
            with patch.dict(sys.modules, {"faster_whisper": fake}):
                with self.assertRaisesRegex(TypeError, "Unexpected unrelated error"):
                    transcribe_with_local_whisper(media)


if __name__ == "__main__":
    unittest.main()
