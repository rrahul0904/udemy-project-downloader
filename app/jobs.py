from __future__ import annotations

import asyncio
import os
import shutil
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from yt_dlp.cookies import YDLLogger, extract_cookies_from_browser

from .practice_tests import PracticeExportError, export_practice_tests
from .safety import slug_from_url


SUPPORTED_BROWSER_COOKIES = {"brave", "chrome", "chromium", "edge", "firefox", "opera", "safari", "vivaldi"}


@dataclass
class JobConfig:
    course_url: str
    auth_method: str
    browser: str | None
    quality: str
    subtitles: bool
    auto_subtitles: bool
    subtitle_languages: str
    include_practice_tests: bool


@dataclass
class Job:
    id: str
    config: JobConfig
    output_dir: Path
    status: str = "queued"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    logs: list[str] = field(default_factory=list)
    return_code: int | None = None
    process: asyncio.subprocess.Process | None = field(default=None, repr=False)
    task: asyncio.Task[Any] | None = field(default=None, repr=False)

    def add_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        clean = message.rstrip()
        if clean:
            self.logs.append(f"[{timestamp}] {clean}")
            self.logs = self.logs[-500:]
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "return_code": self.return_code,
            "course_url": self.config.course_url,
            "auth_method": self.config.auth_method,
            "browser": self.config.browser,
            "quality": self.config.quality,
            "include_practice_tests": self.config.include_practice_tests,
            "output_dir": str(self.output_dir),
            "logs": self.logs,
        }


class JobManager:
    def __init__(self, downloads_dir: Path, data_dir: Path):
        self.downloads_dir = downloads_dir
        self.data_dir = data_dir
        self.cookies_dir = data_dir / "cookies"
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.cookies_dir.mkdir(parents=True, exist_ok=True)
        self.jobs: dict[str, Job] = {}

    async def create_job(self, config: JobConfig, cookies_bytes: bytes | None) -> Job:
        job_id = uuid.uuid4().hex
        slug = slug_from_url(config.course_url)
        output_dir = self.downloads_dir / f"{slug}-{job_id[:8]}"
        output_dir.mkdir(parents=True, exist_ok=True)
        cookies_path: Path | None = None

        if config.auth_method == "cookies_file":
            if not cookies_bytes:
                raise ValueError("Cookies file is required for cookies-file auth.")
            cookies_path = self.cookies_dir / f"{job_id}.txt"
            cookies_path.write_bytes(cookies_bytes)
            os.chmod(cookies_path, 0o600)

        job = Job(id=job_id, config=config, output_dir=output_dir)
        job.add_log("Job queued.")
        self.jobs[job_id] = job
        job.task = asyncio.create_task(self._run_job(job, cookies_path))
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def list(self) -> list[Job]:
        return sorted(self.jobs.values(), key=lambda item: item.created_at, reverse=True)

    async def cancel(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job:
            return False
        if job.status not in {"queued", "running"}:
            return True
        job.status = "cancelled"
        job.add_log("Cancellation requested.")
        if job.process and job.process.returncode is None:
            job.process.terminate()
            try:
                await asyncio.wait_for(job.process.wait(), timeout=10)
            except asyncio.TimeoutError:
                job.process.kill()
        return True

    async def _run_job(self, job: Job, cookies_path: Path | None) -> None:
        job.status = "running"
        job.add_log("Starting yt-dlp.")

        try:
            if cookies_path is None:
                cookies_path = await self._extract_browser_cookies(job)

            command = self._build_command(job, cookies_path)
            job.add_log("Downloader command prepared.")
            job.process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(job.output_dir),
            )
            assert job.process.stdout is not None
            while True:
                line = await job.process.stdout.readline()
                if not line:
                    break
                job.add_log(line.decode("utf-8", errors="replace").strip())

            job.return_code = await job.process.wait()
            job.add_log(f"yt-dlp finished with exit code {job.return_code}.")

            if job.status == "cancelled":
                return

            if job.config.include_practice_tests:
                await self._export_practice_tests(job, cookies_path)

            job.status = "succeeded" if job.return_code == 0 else "failed"
        except FileNotFoundError:
            job.status = "failed"
            job.add_log("yt-dlp was not found in the server Python environment.")
        except Exception as exc:
            job.status = "failed"
            job.add_log(f"Job failed: {exc}")
        finally:
            try:
                if cookies_path:
                    cookies_path.unlink(missing_ok=True)
                    job.add_log("Temporary cookies file removed from app storage.")
            finally:
                job.updated_at = datetime.now(timezone.utc).isoformat()

    async def _extract_browser_cookies(self, job: Job) -> Path:
        browser = job.config.browser or ""
        if browser not in SUPPORTED_BROWSER_COOKIES:
            raise ValueError("Unsupported local browser selection.")

        cookies_path = self.cookies_dir / f"{job.id}.txt"
        job.add_log(f"Reading cookies from local {browser} profile.")
        await asyncio.to_thread(self._save_browser_cookies, browser, cookies_path)
        os.chmod(cookies_path, 0o600)
        job.add_log("Browser cookies loaded for this job.")
        return cookies_path

    @staticmethod
    def _save_browser_cookies(browser: str, cookies_path: Path) -> None:
        jar = extract_cookies_from_browser(browser, logger=YDLLogger())
        jar.filename = str(cookies_path)
        jar.save(str(cookies_path), ignore_discard=True, ignore_expires=True)

    def _build_command(self, job: Job, cookies_path: Path) -> list[str]:
        config = job.config
        command = [
            sys.executable,
            str(Path(__file__).with_name("yt_dlp_truststore.py")),
            "--cookies",
            str(cookies_path),
            "--paths",
            str(job.output_dir),
            "--output",
            "%(playlist_title)s/%(playlist_index)03d - %(title)s.%(ext)s",
            "--output-na-placeholder",
            "Unknown",
            "--download-archive",
            str(job.output_dir / ".download-archive.txt"),
            "--continue",
            "--ignore-errors",
            "--no-abort-on-error",
            "--newline",
            "--restrict-filenames",
            "--write-description",
            "--write-info-json",
            "--write-thumbnail",
            "--merge-output-format",
            "mp4",
            "--concurrent-fragments",
            "4",
            "--retries",
            "10",
            "--fragment-retries",
            "10",
            "--sleep-requests",
            "1",
        ]

        fmt = self._format_selector(config.quality)
        if fmt:
            command.extend(["--format", fmt])

        if config.subtitles:
            command.extend(["--write-subs", "--embed-subs"])
        if config.auto_subtitles:
            command.extend(["--write-auto-subs"])
        if config.subtitles or config.auto_subtitles:
            command.extend(["--sub-langs", config.subtitle_languages or "en.*"])

        command.append(self._yt_dlp_course_url(config.course_url))
        return command

    @staticmethod
    def _yt_dlp_course_url(course_url: str) -> str:
        parsed = urlparse(course_url)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] == "course":
            return urlunparse((parsed.scheme, parsed.netloc, f"/{parts[1]}/", "", parsed.query, ""))
        return course_url

    async def _export_practice_tests(self, job: Job, cookies_path: Path) -> None:
        job.add_log("Exporting practice tests and quizzes.")
        practice_dir = job.output_dir / "_practice-tests"
        try:
            result = await asyncio.to_thread(
                export_practice_tests, job.config.course_url, cookies_path, practice_dir
            )
        except PracticeExportError as exc:
            job.add_log(f"Practice test export skipped: {exc}")
            return
        except Exception as exc:
            job.add_log(f"Practice test export failed: {exc}")
            return

        job.add_log(
            "Practice test export complete: "
            f"{result.item_count} item(s), {result.assessment_count} question(s)."
        )
        if result.warnings:
            job.add_log(f"Practice export warnings: {len(result.warnings)}. See practice-tests.html.")

    @staticmethod
    def _format_selector(quality: str) -> str | None:
        if quality == "best":
            return None
        if quality in {"1080", "720", "480", "360"}:
            return f"bv*[height<={quality}]+ba/b[height<={quality}]/best[height<={quality}]"
        return None


def disk_usage(path: Path) -> dict[str, int]:
    total, used, free = shutil.disk_usage(path)
    return {"total": total, "used": used, "free": free}
