"""Regression tests for independent Udemy practice-test exports."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.jobs import Job, JobConfig, JobManager


class PracticeOnlyJobTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manager = JobManager(self.root / "downloads", self.root / "data")
        self.config = JobConfig(
            course_url="https://www.udemy.com/course/example/",
            platform="udemy", auth_method="cookies_file", browser=None,
            quality="best", subtitles=True, auto_subtitles=False,
            subtitle_languages="en.*", include_practice_tests=True,
            download_videos=False,
        )
        self.job = Job(id="practice-test", config=self.config, output_dir=self.root / "downloads" / "practice-test")
        self.job.output_dir.mkdir()

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def test_practice_only_never_starts_video_downloader(self):
        cookies = self.root / "data" / "cookies" / "test.txt"
        cookies.write_text("temporary credentials", encoding="utf-8")
        with patch.object(self.manager, "_build_command", side_effect=AssertionError("video downloader invoked")):
            with patch.object(self.manager, "_export_practice_tests", new_callable=AsyncMock, return_value=True) as exporter:
                await self.manager._run_job(self.job, cookies)
        self.assertEqual(self.job.status, "succeeded")
        exporter.assert_awaited_once()
        self.assertFalse(cookies.exists())

    async def test_empty_or_rejected_export_marks_job_failed(self):
        cookies = self.root / "data" / "cookies" / "test.txt"
        cookies.write_text("temporary credentials", encoding="utf-8")
        with patch.object(self.manager, "_export_practice_tests", new_callable=AsyncMock, return_value=False):
            await self.manager._run_job(self.job, cookies)
        self.assertEqual(self.job.status, "failed")
        self.assertTrue(any("Practice export failed" in log for log in self.job.logs))

    async def test_legacy_persisted_config_defaults_to_video_download(self):
        import dataclasses
        legacy = dataclasses.asdict(self.config)
        legacy.pop("download_videos")
        restored = JobConfig(**legacy)
        self.assertTrue(restored.download_videos)


if __name__ == "__main__":
    unittest.main()
