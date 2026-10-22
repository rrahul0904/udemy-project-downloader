from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from yt_dlp.cookies import YDLLogger, extract_cookies_from_browser

from .practice_tests import PracticeExportError, export_practice_tests
from .safety import slug_from_url

SUPPORTED_BROWSER_COOKIES = {"brave", "chrome", "chromium", "edge", "firefox", "opera", "safari", "vivaldi"}
MIN_FREE_BYTES = 256 * 1024 * 1024
LOG_PERSIST_INTERVAL = 25
MEDIA_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".m4a", ".mp3", ".aac", ".ogg", ".opus"}


@dataclass
class JobConfig:
    course_url: str
    platform: str
    auth_method: str
    browser: str | None
    quality: str
    subtitles: bool
    auto_subtitles: bool
    subtitle_languages: str
    include_practice_tests: bool
    download_videos: bool = True


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
    component_statuses: dict[str, str] = field(default_factory=dict)
    practice_validation: dict[str, Any] | None = None
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
            "platform": self.config.platform,
            "auth_method": self.config.auth_method,
            "browser": self.config.browser,
            "quality": self.config.quality,
            "include_practice_tests": self.config.include_practice_tests,
            "download_videos": self.config.download_videos,
            "component_statuses": self.component_statuses,
            "practice_validation": self.practice_validation,
            "output_dir": str(self.output_dir),
            "logs": self.logs,
        }

    def persistent_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "config": asdict(self.config),
            "output_dir": str(self.output_dir),
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "logs": self.logs,
            "return_code": self.return_code,
            "component_statuses": self.component_statuses,
            "practice_validation": self.practice_validation,
        }


class JobManager:
    def __init__(self, downloads_dir: Path, data_dir: Path, max_concurrent_jobs: int = 2):
        self.downloads_dir = downloads_dir
        self.data_dir = data_dir
        self.cookies_dir = data_dir / "cookies"
        self.state_path = data_dir / "jobs.json"
        self.max_download_bytes = max(0, int(os.getenv("MAX_DOWNLOAD_BYTES", "0") or 0))
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.cookies_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.cookies_dir, 0o700)
        self.jobs: dict[str, Job] = {}
        self._semaphore = asyncio.Semaphore(max(1, max_concurrent_jobs))
        self._load_state()
        self._cleanup_stale_cookies()

    def _load_state(self) -> None:
        if not self.state_path.is_file():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return
        for item in payload.get("jobs", []) if isinstance(payload, dict) else []:
            try:
                job = Job(
                    id=item["id"],
                    config=JobConfig(**item["config"]),
                    output_dir=Path(item["output_dir"]),
                    status=item.get("status", "failed"),
                    created_at=item.get("created_at") or datetime.now(timezone.utc).isoformat(),
                    updated_at=item.get("updated_at") or datetime.now(timezone.utc).isoformat(),
                    logs=list(item.get("logs") or [])[-500:],
                    return_code=item.get("return_code"),
                    component_statuses=dict(item.get("component_statuses") or {}),
                    practice_validation=item.get("practice_validation"),
                )
            except (KeyError, TypeError, ValueError):
                continue
            if job.status in {"queued", "running"}:
                job.status = "failed"
                job.add_log("Previous process was interrupted by an application restart; retry the job explicitly.")
            self.jobs[job.id] = job
        self._persist()

    def _persist(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temp = self.state_path.with_suffix(".tmp")
        payload = {"jobs": [job.persistent_dict() for job in self.list()[:500]]}
        temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.chmod(temp, 0o600)
        temp.replace(self.state_path)

    def _cleanup_stale_cookies(self) -> None:
        for path in self.cookies_dir.glob("*.txt"):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def _log(self, job: Job, message: str, *, persist: bool = True) -> None:
        job.add_log(message)
        if persist:
            self._persist()

    async def create_job(self, config: JobConfig, cookies_bytes: bytes | None) -> Job:
        _, _, free = shutil.disk_usage(self.downloads_dir)
        if free < MIN_FREE_BYTES:
            raise RuntimeError("Insufficient free disk space to start a download job.")

        job_id = uuid.uuid4().hex
        slug = slug_from_url(config.course_url)
        output_dir = self.downloads_dir / f"{slug}-{job_id[:8]}"
        output_dir.mkdir(parents=True, exist_ok=True)
        cookies_path: Path | None = None

        if config.auth_method == "cookies_file":
            if not cookies_bytes:
                raise ValueError("Cookies file is required for cookies-file auth.")
            cookies_path = self.cookies_dir / f"{job_id}.txt"
            with os.fdopen(os.open(cookies_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as file:
                file.write(cookies_bytes)

        job = Job(id=job_id, config=config, output_dir=output_dir)
        job.component_statuses = {
            "video": "queued" if config.download_videos else "not_requested",
            "practice": "queued" if config.include_practice_tests else "not_requested",
        }
        job.add_log("Job queued.")
        self.jobs[job_id] = job
        self._persist()
        job.task = asyncio.create_task(self._run_bounded(job, cookies_path))
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
        was_queued = job.status == "queued"
        job.status = "cancelled"
        for component, status in job.component_statuses.items():
            if status in {"queued", "running"}:
                job.component_statuses[component] = "cancelled"
        self._log(job, "Cancellation requested.")
        if job.process and job.process.returncode is None:
            job.process.terminate()
            try:
                await asyncio.wait_for(job.process.wait(), timeout=10)
            except asyncio.TimeoutError:
                job.process.kill()
                await job.process.wait()
        elif was_queued and job.task and not job.task.done():
            job.task.cancel()
            (self.cookies_dir / f"{job.id}.txt").unlink(missing_ok=True)
        # A running threaded exporter cannot be stopped safely. Let it finish,
        # then _run_job observes the cancellation before setting a final status.
        self._persist()
        return True

    async def _run_bounded(self, job: Job, cookies_path: Path | None) -> None:
        try:
            async with self._semaphore:
                if job.status == "cancelled":
                    return
                await self._run_job(job, cookies_path)
        except asyncio.CancelledError:
            if job.status != "cancelled":
                job.status = "cancelled"
                self._log(job, "Job task cancelled.")
            raise

    async def _run_job(self, job: Job, cookies_path: Path | None) -> None:
        job.status = "running"
        job.component_statuses.setdefault("video", "queued" if job.config.download_videos else "not_requested")
        job.component_statuses.setdefault(
            "practice", "queued" if job.config.include_practice_tests else "not_requested"
        )
        try:
            if cookies_path is None and job.config.auth_method == "browser":
                try:
                    cookies_path = await self._extract_browser_cookies(job)
                except Exception as exc:
                    auth_status = "failed" if isinstance(exc, ValueError) else "not_accessible"
                    for component, status in job.component_statuses.items():
                        if status == "queued":
                            job.component_statuses[component] = auth_status
                    job.status = auth_status
                    self._log(job, f"Browser authentication unavailable: {type(exc).__name__}.")
                    return
            if job.status == "cancelled":
                return

            if job.config.download_videos:
                job.component_statuses["video"] = "running"
                try:
                    await self._run_video(job, cookies_path)
                except Exception as exc:
                    job.component_statuses["video"] = "failed"
                    self._log(job, f"Video download failed: {type(exc).__name__}: {exc}")
                if job.status == "cancelled":
                    return
            else:
                job.return_code = 0
                job.component_statuses["video"] = "not_requested"
                self._log(job, "Practice-only job: video download skipped.")

            practice_status = "not_requested"
            if job.config.include_practice_tests and job.config.platform == "udemy":
                job.component_statuses["practice"] = "running"
                practice_status = await self._export_practice_tests(job, cookies_path)
                # Older test doubles may still return a boolean.
                if isinstance(practice_status, bool):
                    practice_status = "succeeded" if practice_status else "failed"
                job.component_statuses["practice"] = "cancelled" if job.status == "cancelled" else practice_status
            elif job.config.include_practice_tests:
                practice_status = "no_practice_tests"
                job.component_statuses["practice"] = practice_status

            if job.status == "cancelled":
                return
            video_status = job.component_statuses.get("video", "not_requested")
            job.status = self._overall_status(video_status, practice_status)
            if video_status in {"failed", "partial"}:
                self._log(job, f"Video download {video_status}; check the yt-dlp output.")
            if practice_status not in {"not_requested", "succeeded"}:
                self._log(job, f"Practice export status: {practice_status}.")
                if practice_status == "failed":
                    self._log(job, "Practice export failed or no questions were retrieved.")
            self._persist()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            for component, status in job.component_statuses.items():
                if status == "running":
                    job.component_statuses[component] = "failed"
            job.status = self._overall_status(
                job.component_statuses.get("video", "not_requested"),
                job.component_statuses.get("practice", "not_requested"),
            )
            self._log(job, f"Job failed: {type(exc).__name__}: {exc}")
        finally:
            job.process = None
            try:
                if cookies_path:
                    cookies_path.unlink(missing_ok=True)
                    self._log(job, "Temporary cookies file removed from app storage.")
            finally:
                job.updated_at = datetime.now(timezone.utc).isoformat()
                self._persist()

    async def _run_video(self, job: Job, cookies_path: Path | None) -> None:
        self._log(job, "Starting yt-dlp.")
        command = self._build_command(job, cookies_path)
        self._log(job, "Downloader command prepared.")
        job.process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        log_lines = 0
        downloader_errors = 0
        while True:
            line = await job.process.stdout.readline()
            if not line:
                break
            message = line.decode("utf-8", errors="replace").strip()
            if message.lstrip().startswith("ERROR:"):
                downloader_errors += 1
            self._log(job, message, persist=False)
            log_lines += 1
            if log_lines % LOG_PERSIST_INTERVAL == 0:
                self._persist()
        job.return_code = await job.process.wait()
        if job.status == "cancelled":
            job.component_statuses["video"] = "cancelled"
            self._log(job, "Video download cancelled.")
            return
        media_count = self._media_file_count(job.output_dir)
        if media_count == 0:
            job.component_statuses["video"] = "failed"
        elif job.return_code != 0 or downloader_errors:
            job.component_statuses["video"] = "partial"
        else:
            job.component_statuses["video"] = "succeeded"
        self._log(job, f"yt-dlp finished with exit code {job.return_code}.")
        self._log(job, f"Video result: {media_count} media file(s), {downloader_errors} downloader error(s).")

    @staticmethod
    def _overall_status(video_status: str, practice_status: str) -> str:
        requested = {status for status in (video_status, practice_status) if status != "not_requested"}
        if not requested:
            return "failed"
        if requested == {"succeeded"}:
            return "succeeded"
        if "succeeded" in requested or "partial" in requested:
            return "partial"
        if "failed" in requested:
            return "failed"
        if "not_accessible" in requested:
            return "not_accessible"
        if "no_practice_tests" in requested:
            return "no_practice_tests"
        return "failed"

    @staticmethod
    def _media_file_count(output_dir: Path) -> int:
        root = output_dir.resolve()
        return sum(
            1 for path in output_dir.rglob("*")
            if path.is_file() and path.resolve().is_relative_to(root) and path.suffix.lower() in MEDIA_SUFFIXES
        )

    async def _extract_browser_cookies(self, job: Job) -> Path:
        browser = job.config.browser or ""
        if browser not in SUPPORTED_BROWSER_COOKIES:
            raise ValueError("Unsupported local browser selection.")
        cookies_path = self.cookies_dir / f"{job.id}.txt"
        self._log(job, f"Reading cookies from local {browser} profile.")
        with os.fdopen(os.open(cookies_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"):
            pass
        try:
            await asyncio.to_thread(self._save_browser_cookies, browser, cookies_path)
            os.chmod(cookies_path, 0o600)
        except BaseException:
            cookies_path.unlink(missing_ok=True)
            raise
        self._log(job, "Browser cookies loaded for this job.")
        return cookies_path

    @staticmethod
    def _save_browser_cookies(browser: str, cookies_path: Path) -> None:
        jar = extract_cookies_from_browser(browser, logger=YDLLogger())
        jar.filename = str(cookies_path)
        jar.save(str(cookies_path), ignore_discard=True, ignore_expires=True)

    def _build_command(self, job: Job, cookies_path: Path | None) -> list[str]:
        config = job.config
        command = [
            sys.executable,
            str(Path(__file__).with_name("yt_dlp_truststore.py")),
            "--paths", str(job.output_dir),
            "--output", self._output_template(config.platform),
            "--output-na-placeholder", "Unknown",
            "--download-archive", str(job.output_dir / ".download-archive.txt"),
            "--continue", "--ignore-errors", "--no-abort-on-error", "--newline", "--restrict-filenames",
            "--write-description", "--write-info-json", "--write-thumbnail", "--merge-output-format", "mp4",
            "--concurrent-fragments", "4", "--retries", "10", "--fragment-retries", "10", "--sleep-requests", "1",
        ]
        if self.max_download_bytes:
            command.extend(["--max-filesize", str(self.max_download_bytes)])
        if cookies_path:
            command.extend(["--cookies", str(cookies_path)])
        fmt = self._format_selector(config.quality)
        if fmt:
            command.extend(["--format", fmt])
        if config.subtitles:
            command.extend(["--write-subs", "--embed-subs"])
        if config.auto_subtitles:
            command.extend(["--write-auto-subs"])
        if config.subtitles or config.auto_subtitles:
            command.extend(["--sub-langs", config.subtitle_languages or "en.*"])
        if config.platform == "youtube" and not self._is_explicit_youtube_playlist(config.course_url):
            command.append("--no-playlist")
        command.append(self._yt_dlp_url(config))
        return command

    @staticmethod
    def _yt_dlp_url(config: JobConfig) -> str:
        if config.platform != "udemy":
            return config.course_url
        parsed = urlparse(config.course_url)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] == "course":
            return urlunparse((parsed.scheme, parsed.netloc, f"/{parts[1]}/", "", parsed.query, ""))
        return config.course_url

    async def _export_practice_tests(self, job: Job, cookies_path: Path | None) -> str:
        if not cookies_path:
            self._log(job, "Practice test export skipped: Udemy authentication cookies are required.")
            return "not_accessible"
        self._log(job, "Exporting practice tests and quizzes.")
        practice_dir = job.output_dir / "_practice-tests"
        try:
            result = await asyncio.to_thread(export_practice_tests, job.config.course_url, cookies_path, practice_dir)
        except PracticeExportError as exc:
            self._log(job, f"Practice test export skipped: {exc}")
            return "failed"
        except Exception as exc:
            self._log(job, f"Practice test export failed: {type(exc).__name__}: {exc}")
            return "failed"
        job.practice_validation = result.validation
        self._log(job, f"Practice test export complete: {result.item_count} item(s), {result.assessment_count} question(s).")
        self._log(job, f"Practice test files written to {practice_dir}.")
        if result.assessment_count:
            self._log(job, f"Practice test PDF ready: {result.output_pdf.name}.")
        else:
            self._log(job, f"Diagnostic PDF only (no questions): {result.output_pdf.name}.")
        if result.output_set_pdfs:
            self._log(job, f"Practice set PDFs ready: {len(result.output_set_pdfs)} file(s).")
        if result.warnings:
            self._log(job, f"Practice export warnings: {len(result.warnings)}. See {result.output_html.name}.")
        if result.assessment_count == 0:
            self._log(job, "No practice questions retrieved; this job is not verified as a successful exam export.")
        status = (result.validation or {}).get("status")
        return status if status in {"succeeded", "partial", "failed", "not_accessible", "no_practice_tests"} else "failed"

    @staticmethod
    def _format_selector(quality: str) -> str | None:
        if quality == "best":
            return None
        if quality in {"1080", "720", "480", "360"}:
            return f"bv*[height<={quality}]+ba/b[height<={quality}]/best[height<={quality}]"
        return None

    @staticmethod
    def _output_template(platform: str) -> str:
        if platform == "youtube":
            return "%(title)s [%(id)s].%(ext)s"
        return "%(playlist_title)s/%(playlist_index)03d - %(title)s.%(ext)s"

    @staticmethod
    def _is_explicit_youtube_playlist(url: str) -> bool:
        parsed = urlparse(url)
        parts = [part for part in parsed.path.split("/") if part]
        return parts[:1] == ["playlist"]


def disk_usage(path: Path) -> dict[str, int]:
    total, used, free = shutil.disk_usage(path)
    return {"total": total, "used": used, "free": free}
