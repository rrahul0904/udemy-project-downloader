from __future__ import annotations

import asyncio
import json
import os
import re
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
ALLOWED_MEDIA_MODES = {"video", "audio"}
ALLOWED_AUDIO_FORMATS = {"best", "mp3", "m4a", "opus", "flac", "wav", "aac", "vorbis"}
ALLOWED_OUTPUT_CONTAINERS = {"mp4", "webm", "mkv"}
ALLOWED_SUBTITLE_FORMATS = {"best", "srt", "vtt", "ass", "lrc"}
_SPEED_LIMIT_RE = re.compile(r"^[1-9]\d*(?:\.\d+)?[KMG]?$", re.IGNORECASE)
_PLAYLIST_ITEMS_RE = re.compile(r"^\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*$")


def _time_marker_seconds(value: str) -> float:
    marker = (value or "").strip()
    if not marker:
        raise ValueError("Trim markers cannot be empty.")
    if ":" not in marker:
        try:
            seconds = float(marker)
        except ValueError as exc:
            raise ValueError("Trim markers must be seconds or MM:SS / HH:MM:SS.") from exc
        if seconds < 0:
            raise ValueError("Trim markers cannot be negative.")
        return seconds
    parts = marker.split(":")
    if len(parts) not in {2, 3} or any(not part.isdigit() for part in parts):
        raise ValueError("Trim markers must be seconds or MM:SS / HH:MM:SS.")
    numbers = [int(part) for part in parts]
    if len(parts) == 2:
        minutes, seconds = numbers
        if seconds >= 60:
            raise ValueError("Trim seconds must be below 60.")
        return minutes * 60 + seconds
    hours, minutes, seconds = numbers
    if minutes >= 60 or seconds >= 60:
        raise ValueError("Trim minutes and seconds must be below 60.")
    return hours * 3600 + minutes * 60 + seconds


def is_explicit_youtube_playlist(url: str) -> bool:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    return parts[:1] == ["playlist"]




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
    media_mode: str = "video"
    audio_format: str = "mp3"
    normalize_audio: bool = False
    sponsorblock: bool = False
    trim_start: str = ""
    trim_end: str = ""
    speed_limit: str = ""
    concurrent_fragments: int = 4
    output_container: str = "mp4"
    subtitle_format: str = "best"
    playlist_items: str = ""


def validate_job_config(config: JobConfig) -> None:
    if config.media_mode not in ALLOWED_MEDIA_MODES:
        raise ValueError("Unsupported media mode.")
    if config.audio_format not in ALLOWED_AUDIO_FORMATS:
        raise ValueError("Unsupported audio format.")
    if config.output_container not in ALLOWED_OUTPUT_CONTAINERS:
        raise ValueError("Unsupported video output container.")
    if config.subtitle_format not in ALLOWED_SUBTITLE_FORMATS:
        raise ValueError("Unsupported subtitle format.")
    if not 1 <= int(config.concurrent_fragments) <= 20:
        raise ValueError("Concurrent fragments must be between 1 and 20.")
    if config.speed_limit and not _SPEED_LIMIT_RE.fullmatch(config.speed_limit):
        raise ValueError("Speed limit must look like 500K, 2M, or 1.5M.")
    if bool(config.trim_start) != bool(config.trim_end):
        raise ValueError("Provide both trim start and trim end.")
    if config.trim_start and config.trim_end:
        if _time_marker_seconds(config.trim_start) >= _time_marker_seconds(config.trim_end):
            raise ValueError("Trim end must be after trim start.")
    if config.playlist_items:
        if not _PLAYLIST_ITEMS_RE.fullmatch(config.playlist_items):
            raise ValueError("Playlist items must use comma-separated indexes or ranges such as 1,3-5.")
        if config.platform != "youtube" or not is_explicit_youtube_playlist(config.course_url):
            raise ValueError("Playlist item selection requires an explicit YouTube playlist URL.")
    if config.sponsorblock and config.platform != "youtube":
        raise ValueError("SponsorBlock is available only for YouTube jobs.")
    if config.normalize_audio and config.media_mode != "audio":
        raise ValueError("Audio normalization requires audio-only mode.")


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
            "platform": self.config.platform,
            "auth_method": self.config.auth_method,
            "browser": self.config.browser,
            "quality": self.config.quality,
            "media_mode": self.config.media_mode,
            "audio_format": self.config.audio_format,
            "normalize_audio": self.config.normalize_audio,
            "sponsorblock": self.config.sponsorblock,
            "trim_start": self.config.trim_start,
            "trim_end": self.config.trim_end,
            "speed_limit": self.config.speed_limit,
            "concurrent_fragments": self.config.concurrent_fragments,
            "output_container": self.config.output_container,
            "subtitle_format": self.config.subtitle_format,
            "playlist_items": self.config.playlist_items,
            "include_practice_tests": self.config.include_practice_tests,
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
        validate_job_config(config)
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
            cookies_path.write_bytes(cookies_bytes)
            os.chmod(cookies_path, 0o600)

        job = Job(id=job_id, config=config, output_dir=output_dir)
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
        job.status = "cancelled"
        self._log(job, "Cancellation requested.")
        if job.process and job.process.returncode is None:
            job.process.terminate()
            try:
                await asyncio.wait_for(job.process.wait(), timeout=10)
            except asyncio.TimeoutError:
                job.process.kill()
                await job.process.wait()
        elif job.task and not job.task.done():
            job.task.cancel()
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
        self._log(job, "Starting yt-dlp.")

        try:
            if cookies_path is None and job.config.auth_method == "browser":
                cookies_path = await self._extract_browser_cookies(job)

            command = self._build_command(job, cookies_path)
            self._log(job, "Downloader command prepared.")
            job.process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(job.output_dir),
            )
            assert job.process.stdout is not None
            log_lines = 0
            while True:
                line = await job.process.stdout.readline()
                if not line:
                    break
                self._log(job, line.decode("utf-8", errors="replace").strip(), persist=False)
                log_lines += 1
                if log_lines % LOG_PERSIST_INTERVAL == 0:
                    self._persist()

            job.return_code = await job.process.wait()
            self._log(job, f"yt-dlp finished with exit code {job.return_code}.")

            if job.status == "cancelled":
                return

            if job.config.include_practice_tests and job.config.platform == "udemy":
                await self._export_practice_tests(job, cookies_path)

            job.status = "succeeded" if job.return_code == 0 else "failed"
            self._persist()
        except FileNotFoundError:
            job.status = "failed"
            self._log(job, "yt-dlp was not found in the server Python environment.")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            job.status = "failed"
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

    async def _extract_browser_cookies(self, job: Job) -> Path:
        browser = job.config.browser or ""
        if browser not in SUPPORTED_BROWSER_COOKIES:
            raise ValueError("Unsupported local browser selection.")
        cookies_path = self.cookies_dir / f"{job.id}.txt"
        self._log(job, f"Reading cookies from local {browser} profile.")
        await asyncio.to_thread(self._save_browser_cookies, browser, cookies_path)
        os.chmod(cookies_path, 0o600)
        self._log(job, "Browser cookies loaded for this job.")
        return cookies_path

    @staticmethod
    def _save_browser_cookies(browser: str, cookies_path: Path) -> None:
        jar = extract_cookies_from_browser(browser, logger=YDLLogger())
        jar.filename = str(cookies_path)
        jar.save(str(cookies_path), ignore_discard=True, ignore_expires=True)

    def _build_command(self, job: Job, cookies_path: Path | None) -> list[str]:
        config = job.config
        validate_job_config(config)
        command = [
            sys.executable,
            str(Path(__file__).with_name("yt_dlp_truststore.py")),
            "--paths", str(job.output_dir),
            "--output", self._output_template(config.platform),
            "--output-na-placeholder", "Unknown",
            "--download-archive", str(job.output_dir / ".download-archive.txt"),
            "--continue", "--ignore-errors", "--no-abort-on-error", "--newline", "--restrict-filenames",
            "--write-description", "--write-info-json", "--write-thumbnail",
            "--concurrent-fragments", str(config.concurrent_fragments),
            "--retries", "10", "--fragment-retries", "10", "--sleep-requests", "1",
        ]
        if self.max_download_bytes:
            command.extend(["--max-filesize", str(self.max_download_bytes)])
        if cookies_path:
            command.extend(["--cookies", str(cookies_path)])

        if config.media_mode == "audio":
            command.extend(["--format", "bestaudio/best", "--extract-audio"])
            if config.audio_format != "best":
                command.extend(["--audio-format", config.audio_format])
            if config.normalize_audio:
                command.extend(["--postprocessor-args", "ffmpeg:-af loudnorm=I=-23:LRA=7:TP=-2"])
        else:
            command.extend(["--merge-output-format", config.output_container])
            fmt = self._format_selector(config.quality)
            if fmt:
                command.extend(["--format", fmt])

        if config.sponsorblock:
            command.extend(["--sponsorblock-remove", "sponsor"])
        if config.trim_start and config.trim_end:
            command.extend(["--download-sections", f"*{config.trim_start}-{config.trim_end}"])
        if config.speed_limit:
            command.extend(["--limit-rate", config.speed_limit])
        if config.playlist_items:
            command.extend(["--playlist-items", config.playlist_items])

        if config.subtitles:
            command.append("--write-subs")
            if config.media_mode == "video":
                command.append("--embed-subs")
        if config.auto_subtitles:
            command.append("--write-auto-subs")
        if config.subtitles or config.auto_subtitles:
            command.extend(["--sub-langs", config.subtitle_languages or "en.*"])
            if config.subtitle_format != "best":
                command.extend(["--sub-format", config.subtitle_format])
        if config.platform == "youtube" and not is_explicit_youtube_playlist(config.course_url):
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

    async def _export_practice_tests(self, job: Job, cookies_path: Path | None) -> None:
        if not cookies_path:
            self._log(job, "Practice test export skipped: Udemy authentication cookies are required.")
            return
        self._log(job, "Exporting practice tests and quizzes.")
        practice_dir = job.output_dir / "_practice-tests"
        try:
            result = await asyncio.to_thread(export_practice_tests, job.config.course_url, cookies_path, practice_dir)
        except PracticeExportError as exc:
            self._log(job, f"Practice test export skipped: {exc}")
            return
        except Exception as exc:
            self._log(job, f"Practice test export failed: {type(exc).__name__}: {exc}")
            return
        self._log(job, f"Practice test export complete: {result.item_count} item(s), {result.assessment_count} question(s).")
        self._log(job, f"Practice test files written to {practice_dir}.")
        self._log(job, f"Practice test PDF ready: {result.output_pdf.name}.")
        if result.output_set_pdfs:
            self._log(job, f"Practice set PDFs ready: {len(result.output_set_pdfs)} file(s).")
        if result.warnings:
            self._log(job, f"Practice export warnings: {len(result.warnings)}. See {result.output_html.name}.")

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

def disk_usage(path: Path) -> dict[str, int]:
    total, used, free = shutil.disk_usage(path)
    return {"total": total, "used": used, "free": free}
