import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from app.jobs import Job, JobConfig, JobManager, validate_job_config


ROOT = Path(__file__).resolve().parents[1]


class ProductionRuntimeTests(unittest.TestCase):
    def test_interrupted_job_is_reconciled_on_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            downloads = root / "downloads"
            data = root / "data"
            manager = JobManager(downloads, data, max_concurrent_jobs=1)
            config = JobConfig(
                course_url="https://www.youtube.com/watch?v=fixture",
                platform="youtube",
                auth_method="none",
                browser=None,
                quality="720",
                subtitles=True,
                auto_subtitles=False,
                subtitle_languages="en.*",
                include_practice_tests=False,
            )
            job = Job(id="restart-fixture", config=config, output_dir=downloads / "fixture", status="running")
            manager.jobs[job.id] = job
            manager._persist()

            reopened = JobManager(downloads, data, max_concurrent_jobs=1)
            restored = reopened.get(job.id)
            self.assertIsNotNone(restored)
            self.assertEqual(restored.status, "failed")
            self.assertTrue(any("interrupted" in line.lower() for line in restored.logs))

    def test_job_command_preserves_safety_and_metadata_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager = JobManager(root / "downloads", root / "data", max_concurrent_jobs=1)
            config = JobConfig(
                course_url="https://www.youtube.com/watch?v=fixture",
                platform="youtube",
                auth_method="none",
                browser=None,
                quality="720",
                subtitles=True,
                auto_subtitles=True,
                subtitle_languages="en.*",
                include_practice_tests=False,
            )
            job = Job(id="command-fixture", config=config, output_dir=root / "downloads" / "fixture")
            command = manager._build_command(job, None)
            joined = " ".join(command)
            self.assertIn("--write-info-json", command)
            self.assertIn("--write-subs", command)
            self.assertIn("--write-auto-subs", command)
            self.assertIn("--download-archive", command)
            self.assertIn("--no-playlist", command)
            self.assertNotIn("--cookies", command)
            self.assertIn("height<=720", joined)

    def test_audio_media_options_map_to_bounded_yt_dlp_arguments(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager = JobManager(root / "downloads", root / "data", max_concurrent_jobs=1)
            config = JobConfig(
                course_url="https://www.youtube.com/playlist?list=PLfixture",
                platform="youtube",
                auth_method="none",
                browser=None,
                quality="best",
                subtitles=True,
                auto_subtitles=True,
                subtitle_languages="en.*",
                include_practice_tests=False,
                media_mode="audio",
                audio_format="mp3",
                normalize_audio=True,
                sponsorblock=True,
                trim_start="00:00:10",
                trim_end="00:00:30",
                speed_limit="2M",
                concurrent_fragments=8,
                output_container="mp4",
                subtitle_format="srt",
                playlist_items="1,3-5",
            )
            job = Job(id="audio-fixture", config=config, output_dir=root / "downloads" / "fixture")
            command = manager._build_command(job, None)

            self.assertIn("--extract-audio", command)
            self.assertEqual(command[command.index("--audio-format") + 1], "mp3")
            self.assertIn("ffmpeg:-af loudnorm=I=-23:LRA=7:TP=-2", command)
            self.assertEqual(command[command.index("--sponsorblock-remove") + 1], "sponsor")
            self.assertEqual(command[command.index("--download-sections") + 1], "*00:00:10-00:00:30")
            self.assertEqual(command[command.index("--limit-rate") + 1], "2M")
            self.assertEqual(command[command.index("--concurrent-fragments") + 1], "8")
            self.assertEqual(command[command.index("--sub-format") + 1], "srt")
            self.assertEqual(command[command.index("--playlist-items") + 1], "1,3-5")
            self.assertNotIn("--merge-output-format", command)
            self.assertNotIn("--embed-subs", command)

    def test_media_option_validation_fails_closed(self):
        base = JobConfig(
            course_url="https://www.youtube.com/playlist?list=PLfixture",
            platform="youtube",
            auth_method="none",
            browser=None,
            quality="best",
            subtitles=False,
            auto_subtitles=False,
            subtitle_languages="en.*",
            include_practice_tests=False,
        )
        for bad in (
            replace(base, media_mode="raw"),
            replace(base, audio_format="exe"),
            replace(base, concurrent_fragments=0),
            replace(base, concurrent_fragments=21),
            replace(base, speed_limit="2M;rm"),
            replace(base, trim_start="00:01:00", trim_end="00:00:30"),
            replace(base, trim_start="00:00:10", trim_end=""),
            replace(base, playlist_items="../1"),
            replace(base, normalize_audio=True),
        ):
            with self.subTest(config=bad):
                with self.assertRaises(ValueError):
                    validate_job_config(bad)

        with self.assertRaises(ValueError):
            validate_job_config(replace(base, course_url="https://www.youtube.com/watch?v=fixture", playlist_items="1-3"))

    def test_video_output_container_is_configurable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager = JobManager(root / "downloads", root / "data", max_concurrent_jobs=1)
            config = JobConfig(
                course_url="https://www.youtube.com/watch?v=fixture",
                platform="youtube",
                auth_method="none",
                browser=None,
                quality="1080",
                subtitles=False,
                auto_subtitles=False,
                subtitle_languages="en.*",
                include_practice_tests=False,
                output_container="mkv",
            )
            job = Job(id="video-fixture", config=config, output_dir=root / "downloads" / "fixture")
            command = manager._build_command(job, None)
            self.assertEqual(command[command.index("--merge-output-format") + 1], "mkv")
            self.assertIn("height<=1080", " ".join(command))

    def test_production_security_contract_is_present(self):
        main = (ROOT / "app/main.py").read_text(encoding="utf-8")
        for expected in (
            'APP_ENV == "production"',
            'APP_USER and APP_PASSWORD are required',
            'WWW-Authenticate',
            'Content-Security-Policy',
            'X-Content-Type-Options',
            'Referrer-Policy',
            'X-Frame-Options',
            'JOB_RATE_LIMIT_PER_MINUTE',
            '@app.get("/api/readiness")',
        ):
            self.assertIn(expected, main)

    def test_container_runs_unprivileged_with_healthcheck(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("USER 10001:10001", dockerfile)
        self.assertIn("HEALTHCHECK", dockerfile)
        self.assertIn("ffmpeg", dockerfile)

    def test_environment_example_does_not_contain_real_secret(self):
        env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("APP_PASSWORD=change-me", env_example)
        self.assertNotIn("ghp_", env_example)
        self.assertNotIn("github_pat_", env_example)


if __name__ == "__main__":
    unittest.main()
