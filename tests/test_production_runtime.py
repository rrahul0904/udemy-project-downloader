import os
import tempfile
import unittest
from pathlib import Path

from app.jobs import Job, JobConfig, JobManager


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
