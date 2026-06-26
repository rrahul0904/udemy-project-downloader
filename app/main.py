from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .jobs import JobConfig, JobManager, SUPPORTED_BROWSER_COOKIES, disk_usage
from .safety import UrlValidationError, normalize_udemy_url

BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent / "static"
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", str(BASE_DIR / "downloads"))).resolve()
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).resolve()
MAX_COOKIES_BYTES = 8 * 1024 * 1024
ALLOWED_QUALITIES = {"best", "1080", "720", "480", "360"}
ALLOWED_AUTH_METHODS = {"cookies_file", "browser"}

app = FastAPI(title="Udemy Project Downloader")
manager = JobManager(DOWNLOAD_DIR, DATA_DIR)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/jobs")
async def create_job(
    course_url: str = Form(...),
    auth_method: str = Form("cookies_file"),
    cookies_file: UploadFile | None = File(None),
    browser: str = Form("chrome"),
    quality: str = Form("best"),
    subtitles: bool = Form(True),
    auto_subtitles: bool = Form(False),
    subtitle_languages: str = Form("en.*"),
    include_practice_tests: bool = Form(True),
    confirm_authorized: bool = Form(False),
) -> dict[str, Any]:
    if not confirm_authorized:
        raise HTTPException(status_code=400, detail="Confirm that you are authorized to archive this course.")

    try:
        normalized_url = normalize_udemy_url(course_url)
    except UrlValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if quality not in ALLOWED_QUALITIES:
        raise HTTPException(status_code=400, detail="Unsupported quality selection.")
    if auth_method not in ALLOWED_AUTH_METHODS:
        raise HTTPException(status_code=400, detail="Unsupported authentication method.")
    if auth_method == "browser" and browser not in SUPPORTED_BROWSER_COOKIES:
        raise HTTPException(status_code=400, detail="Unsupported local browser selection.")

    subtitle_languages = subtitle_languages.strip() or "en.*"
    if len(subtitle_languages) > 80:
        raise HTTPException(status_code=400, detail="Subtitle language filter is too long.")

    cookies_bytes: bytes | None = None
    if auth_method == "cookies_file":
        if not cookies_file:
            raise HTTPException(status_code=400, detail="Upload a Netscape-format cookies.txt file.")
        cookies_bytes = await cookies_file.read()
        if not cookies_bytes:
            raise HTTPException(status_code=400, detail="Upload a Netscape-format cookies.txt file.")
        if len(cookies_bytes) > MAX_COOKIES_BYTES:
            raise HTTPException(status_code=400, detail="Cookies file is larger than 8 MB.")

    config = JobConfig(
        course_url=normalized_url,
        auth_method=auth_method,
        browser=browser if auth_method == "browser" else None,
        quality=quality,
        subtitles=subtitles,
        auto_subtitles=auto_subtitles,
        subtitle_languages=subtitle_languages,
        include_practice_tests=include_practice_tests,
    )
    job = await manager.create_job(config, cookies_bytes)
    return job.as_dict()


@app.get("/api/jobs")
async def list_jobs() -> dict[str, Any]:
    return {"jobs": [job.as_dict() for job in manager.list()]}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job.as_dict()


@app.delete("/api/jobs/{job_id}")
async def cancel_job(job_id: str) -> dict[str, str]:
    cancelled = await manager.cancel(job_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {"status": "cancelled"}


@app.get("/api/downloads")
async def downloads() -> dict[str, Any]:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return {
        "root": str(DOWNLOAD_DIR),
        "usage": disk_usage(DOWNLOAD_DIR),
        "files": _list_downloads(DOWNLOAD_DIR),
    }


@app.get("/files/{relative_path:path}")
async def serve_download(relative_path: str) -> FileResponse:
    target = (DOWNLOAD_DIR / relative_path).resolve()
    if not _is_relative_to(target, DOWNLOAD_DIR) or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(target)


def _list_downloads(root: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if len(files) >= 500:
            break
        rel = path.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        stat = path.stat()
        files.append(
            {
                "path": rel.as_posix(),
                "name": path.name,
                "type": "directory" if path.is_dir() else "file",
                "size": stat.st_size if path.is_file() else None,
                "modified": int(stat.st_mtime),
            }
        )
    return files


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
