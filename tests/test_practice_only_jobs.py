"""Regression tests for independent Udemy practice-test exports."""
import asyncio
import dataclasses
import stat
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
        self.assertEqual(stat.S_IMODE(self.manager.cookies_dir.stat().st_mode), 0o700)
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
        legacy = dataclasses.asdict(self.config)
        legacy.pop("download_videos")
        restored = JobConfig(**legacy)
        self.assertTrue(restored.download_videos)

    async def test_video_only_does_not_call_practice_exporter(self):
        self.job.config = dataclasses.replace(self.config, download_videos=True, include_practice_tests=False)
        (self.job.output_dir / "lesson.mp4").write_bytes(b"synthetic media")
        process = AsyncMock()
        process.stdout.readline = AsyncMock(return_value=b"")
        process.wait = AsyncMock(return_value=0)
        with patch("app.jobs.asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=process), \
             patch.object(self.manager, "_export_practice_tests", side_effect=AssertionError("exporter invoked")):
            await self.manager._run_job(self.job, None)
        self.assertEqual(self.job.status, "succeeded")
        self.assertEqual(self.job.component_statuses["video"], "succeeded")
        self.assertEqual(self.job.component_statuses["practice"], "not_requested")

    async def test_both_components_record_partial_when_practice_fails(self):
        self.job.config = dataclasses.replace(self.config, download_videos=True)
        (self.job.output_dir / "lesson.mp4").write_bytes(b"synthetic media")
        process = AsyncMock()
        process.stdout.readline = AsyncMock(return_value=b"")
        process.wait = AsyncMock(return_value=0)
        cookies = self.root / "data" / "cookies" / "test.txt"
        cookies.write_text("temporary credentials", encoding="utf-8")
        with patch("app.jobs.asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=process), \
             patch.object(self.manager, "_export_practice_tests", new_callable=AsyncMock, return_value="failed") as exporter:
            await self.manager._run_job(self.job, cookies)
        exporter.assert_awaited_once()
        self.assertEqual(self.job.status, "partial")
        self.assertEqual(self.job.component_statuses, {"video": "succeeded", "practice": "failed"})
        self.assertFalse(cookies.exists())

    async def test_exit_zero_without_media_is_video_failure(self):
        self.job.config = dataclasses.replace(self.config, download_videos=True, include_practice_tests=False)
        (self.job.output_dir / "lesson.info.json").write_text("{}", encoding="utf-8")
        process = AsyncMock()
        process.stdout.readline = AsyncMock(return_value=b"")
        process.wait = AsyncMock(return_value=0)
        with patch("app.jobs.asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=process):
            await self.manager._run_job(self.job, None)
        self.assertEqual(self.job.status, "failed")
        self.assertEqual(self.job.component_statuses["video"], "failed")

    async def test_downloaded_media_with_downloader_error_is_partial(self):
        self.job.config = dataclasses.replace(self.config, download_videos=True, include_practice_tests=False)
        (self.job.output_dir / "lesson.mp4").write_bytes(b"synthetic media")
        process = AsyncMock()
        process.stdout.readline = AsyncMock(side_effect=[b"ERROR: one lesson was unavailable\n", b""])
        process.wait = AsyncMock(return_value=0)
        with patch("app.jobs.asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=process):
            await self.manager._run_job(self.job, None)
        self.assertEqual(self.job.status, "partial")
        self.assertEqual(self.job.component_statuses["video"], "partial")

    async def test_video_spawn_failure_still_runs_practice_export(self):
        self.job.config = dataclasses.replace(self.config, download_videos=True)
        cookies = self.root / "data" / "cookies" / "test.txt"
        cookies.write_text("temporary credentials", encoding="utf-8")
        with patch("app.jobs.asyncio.create_subprocess_exec", new_callable=AsyncMock, side_effect=FileNotFoundError), \
             patch.object(self.manager, "_export_practice_tests", new_callable=AsyncMock, return_value="succeeded") as exporter:
            await self.manager._run_job(self.job, cookies)
        exporter.assert_awaited_once()
        self.assertEqual(self.job.component_statuses, {"video": "failed", "practice": "succeeded"})
        self.assertEqual(self.job.status, "partial")
        self.assertFalse(cookies.exists())

    async def test_cancel_during_video_does_not_report_success(self):
        self.job.config = dataclasses.replace(self.config, download_videos=True, include_practice_tests=False)
        process = AsyncMock()
        process.stdout.readline = AsyncMock(return_value=b"")

        async def finish_after_cancellation():
            self.job.status = "cancelled"
            return 0

        process.wait = AsyncMock(side_effect=finish_after_cancellation)
        with patch("app.jobs.asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=process):
            await self.manager._run_job(self.job, None)
        self.assertEqual(self.job.status, "cancelled")
        self.assertEqual(self.job.component_statuses["video"], "cancelled")

    async def test_practice_only_auth_failure_is_not_accessible(self):
        await self.manager._run_job(self.job, None)
        self.assertEqual(self.job.status, "not_accessible")
        self.assertEqual(self.job.component_statuses["practice"], "not_accessible")

    async def test_failed_video_is_not_masked_by_unavailable_practice(self):
        self.assertEqual(self.manager._overall_status("failed", "not_accessible"), "failed")
        self.assertEqual(self.manager._overall_status("failed", "no_practice_tests"), "failed")

    async def test_browser_cookie_failure_updates_both_requested_components(self):
        self.job.config = dataclasses.replace(
            self.config, auth_method="browser", browser="chrome", download_videos=True
        )
        with patch.object(self.manager, "_extract_browser_cookies", new_callable=AsyncMock, side_effect=OSError), \
             patch.object(self.manager, "_build_command", side_effect=AssertionError("video downloader invoked")), \
             patch.object(self.manager, "_export_practice_tests", side_effect=AssertionError("exporter invoked")):
            await self.manager._run_job(self.job, None)
        self.assertEqual(self.job.status, "not_accessible")
        self.assertEqual(
            self.job.component_statuses,
            {"video": "not_accessible", "practice": "not_accessible"},
        )

    async def test_cancelled_queued_job_removes_cookie_and_stays_cancelled(self):
        cookies = self.root / "data" / "cookies" / "practice-test.txt"
        cookies.write_text("temporary credentials", encoding="utf-8")
        self.job.status = "queued"
        self.job.component_statuses = {"video": "not_requested", "practice": "queued"}
        self.job.task = asyncio.create_task(asyncio.sleep(10))
        self.manager.jobs[self.job.id] = self.job
        self.assertTrue(await self.manager.cancel(self.job.id))
        self.assertEqual(self.job.status, "cancelled")
        self.assertEqual(self.job.component_statuses["practice"], "cancelled")
        self.assertFalse(cookies.exists())
        with self.assertRaises(asyncio.CancelledError):
            await self.job.task

    async def test_component_statuses_survive_restart(self):
        self.job.status = "partial"
        self.job.component_statuses = {"video": "succeeded", "practice": "partial"}
        self.job.practice_validation = {"questions_expected": 2, "questions_retrieved": 1}
        self.manager.jobs[self.job.id] = self.job
        self.manager._persist()
        self.assertEqual(stat.S_IMODE(self.manager.state_path.stat().st_mode), 0o600)
        restored = JobManager(self.root / "downloads", self.root / "data")
        self.assertEqual(restored.get(self.job.id).component_statuses, self.job.component_statuses)
        self.assertEqual(restored.get(self.job.id).practice_validation, self.job.practice_validation)


if __name__ == "__main__":
    unittest.main()
