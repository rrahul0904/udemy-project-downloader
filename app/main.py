from __future__ import annotations

import asyncio
import base64
import importlib.util
import os
import secrets
import shutil
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .api_v1 import build_api_v1
from .database import CourseStore
from .jobs import JobConfig, JobManager, SUPPORTED_BROWSER_COOKIES, disk_usage
from .learning_library import load_transcript, search_transcript
from .safety import UrlValidationError, normalize_supported_url

BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent / "static"
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", str(BASE_DIR / "downloads"))).resolve()
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).resolve()
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
APP_USER = os.getenv("APP_USER", "").strip()
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
MAX_COOKIES_BYTES = 8 * 1024 * 1024
MAX_NOTE_BYTES = 256 * 1024
MAX_QUERY_CHARS = 500
MAX_CONCURRENT_JOBS = max(1, min(int(os.getenv("MAX_CONCURRENT_JOBS", "2")), 8))
JOB_RATE_LIMIT_PER_MINUTE = max(1, min(int(os.getenv("JOB_RATE_LIMIT_PER_MINUTE", "5")), 60))
ALLOWED_QUALITIES = {"best", "1080", "720", "480", "360"}
ALLOWED_AUTH_METHODS = {"none", "cookies_file", "browser"}

if APP_ENV == "production" and (not APP_USER or not APP_PASSWORD):
    raise RuntimeError("APP_USER and APP_PASSWORD are required when APP_ENV=production.")

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Course Intelligence",
    version="1.0.0",
    docs_url=None if APP_ENV == "production" else "/docs",
    redoc_url=None if APP_ENV == "production" else "/redoc",
    openapi_url="/api/v1/openapi.json",
)
store = CourseStore(DATA_DIR / "app.db")
manager = JobManager(DOWNLOAD_DIR, DATA_DIR, max_concurrent_jobs=MAX_CONCURRENT_JOBS)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(build_api_v1(store, DOWNLOAD_DIR))
_rate_windows: dict[str, deque[float]] = defaultdict(deque)


class NotePayload(BaseModel):
    body: str = Field(default="", max_length=MAX_NOTE_BYTES)


class BookmarkPayload(BaseModel):
    segment_index: int = Field(ge=0, le=2_000_000)
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    text: str = Field(min_length=1, max_length=4000)


def _unauthorized() -> Response:
    return Response(
        content="Authentication required",
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="Course Intelligence", charset="UTF-8"'},
    )


def _valid_basic_auth(request: Request) -> bool:
    if APP_ENV != "production":
        return True
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth[6:], validate=True).decode("utf-8")
        username, password = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError):
        return False
    return secrets.compare_digest(username, APP_USER) and secrets.compare_digest(password, APP_PASSWORD)


def _same_origin(request: Request) -> bool:
    if APP_ENV != "production" or request.method in {"GET", "HEAD", "OPTIONS"}:
        return True
    origin = request.headers.get("origin")
    if not origin:
        return True
    expected = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    try:
        actual_parts = urlparse(origin)
        expected_parts = urlparse(expected)
    except ValueError:
        return False
    return (actual_parts.scheme, actual_parts.netloc) == (expected_parts.scheme, expected_parts.netloc)


@app.middleware("http")
async def production_boundary(request: Request, call_next):
    if request.url.path != "/api/health" and not _valid_basic_auth(request):
        return _unauthorized()
    if not _same_origin(request):
        return JSONResponse(status_code=403, content={"detail": "Cross-origin state changes are not allowed."})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self' https://api.crossref.org; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/lab")
async def study_lab() -> FileResponse:
    return FileResponse(STATIC_DIR / "lab.html")


@app.get("/learn")
async def course_intelligence() -> FileResponse:
    return FileResponse(STATIC_DIR / "learn.html")


@app.get("/viewer")
async def synchronized_viewer() -> FileResponse:
    return FileResponse(STATIC_DIR / "viewer.html")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/readiness")
async def readiness() -> dict[str, Any]:
    database = await asyncio.to_thread(store.health)
    checks = {
        **database,
        "data_dir": DATA_DIR.is_dir() and os.access(DATA_DIR, os.W_OK),
        "download_dir": DOWNLOAD_DIR.is_dir() and os.access(DOWNLOAD_DIR, os.W_OK),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "yt_dlp": importlib.util.find_spec("yt_dlp") is not None,
    }
    ready = (
        checks["database"] == "ok"
        and checks["data_dir"]
        and checks["download_dir"]
        and checks["ffmpeg"]
        and checks["yt_dlp"]
    )
    if not ready:
        raise HTTPException(status_code=503, detail={"status": "not_ready", "checks": checks})
    return {"status": "ready", "checks": checks}


@app.get("/api/library")
async def course_library() -> dict[str, Any]:
    try:
        return await asyncio.to_thread(store.sync_library, DOWNLOAD_DIR)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Unable to refresh the course library.") from exc


@app.get("/api/learning/transcript")
async def learning_transcript(path: str) -> dict[str, Any]:
    if len(path) > 2048:
        raise HTTPException(status_code=400, detail="Transcript path is too long.")
    try:
        return await asyncio.to_thread(load_transcript, DOWNLOAD_DIR, path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Transcript not found.") from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/learning/search")
async def learning_search(
    q: str,
    path: str | None = None,
    course_id: str | None = None,
    lesson_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    if not q.strip():
        return {"query": q, "hits": [], "count": 0}
    if len(q) > MAX_QUERY_CHARS:
        raise HTTPException(status_code=400, detail="Search query is too long.")
    try:
        if path:
            return await asyncio.to_thread(search_transcript, DOWNLOAD_DIR, path, q, limit)
        return await asyncio.to_thread(store.search, q, course_id=course_id, lesson_id=lesson_id, limit=limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Transcript not found.") from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/learning/lessons/{lesson_id}/notes")
async def lesson_note(lesson_id: str) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(store.get_note, lesson_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Lesson not found.") from exc


@app.put("/api/learning/lessons/{lesson_id}/notes")
async def save_lesson_note(lesson_id: str, payload: NotePayload) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(store.put_note, lesson_id, payload.body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Lesson not found.") from exc


@app.get("/api/learning/lessons/{lesson_id}/bookmarks")
async def lesson_bookmarks(lesson_id: str) -> dict[str, Any]:
    try:
        items = await asyncio.to_thread(store.bookmarks, lesson_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Lesson not found.") from exc
    return {"bookmarks": items}


@app.post("/api/learning/lessons/{lesson_id}/bookmarks")
async def create_bookmark(lesson_id: str, payload: BookmarkPayload) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(
            store.add_bookmark,
            lesson_id,
            payload.segment_index,
            payload.start_ms,
            payload.end_ms,
            payload.text,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Lesson not found.") from exc


@app.delete("/api/learning/bookmarks/{bookmark_id}")
async def delete_bookmark(bookmark_id: str) -> dict[str, str]:
    deleted = await asyncio.to_thread(store.delete_bookmark, bookmark_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Bookmark not found.")
    return {"status": "deleted"}


def _enforce_job_rate_limit(request: Request) -> None:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    client = forwarded or (request.client.host if request.client else "unknown")
    now = time.monotonic()
    window = _rate_windows[client]
    while window and now - window[0] >= 60:
        window.popleft()
    if len(window) >= JOB_RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Too many download jobs. Try again shortly.")
    window.append(now)


@app.post("/api/jobs")
async def create_job(
    request: Request,
    course_url: str = Form(..., max_length=4096),
    auth_method: str = Form("none"),
    cookies_file: UploadFile | None = File(None),
    browser: str = Form("chrome"),
    quality: str = Form("best"),
    subtitles: bool = Form(True),
    auto_subtitles: bool = Form(False),
    subtitle_languages: str = Form("en.*"),
    include_practice_tests: bool = Form(True),
    confirm_authorized: bool = Form(False),
) -> dict[str, Any]:
    _enforce_job_rate_limit(request)
    if not confirm_authorized:
        raise HTTPException(status_code=400, detail="Confirm that you are authorized to archive this content.")

    try:
        normalized = normalize_supported_url(course_url)
    except UrlValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if quality not in ALLOWED_QUALITIES:
        raise HTTPException(status_code=400, detail="Unsupported quality selection.")
    if auth_method not in ALLOWED_AUTH_METHODS:
        raise HTTPException(status_code=400, detail="Unsupported authentication method.")
    if normalized.platform == "udemy" and auth_method == "none":
        raise HTTPException(status_code=400, detail="Udemy downloads require a local browser session or a cookies.txt file.")
    if auth_method == "browser" and browser not in SUPPORTED_BROWSER_COOKIES:
        raise HTTPException(status_code=400, detail="Unsupported local browser selection.")

    subtitle_languages = subtitle_languages.strip() or "en.*"
    if len(subtitle_languages) > 80:
        raise HTTPException(status_code=400, detail="Subtitle language filter is too long.")

    cookies_bytes: bytes | None = None
    if auth_method == "cookies_file":
        if not cookies_file:
            raise HTTPException(status_code=400, detail="Upload a Netscape-format cookies.txt file.")
        cookies_bytes = await cookies_file.read(MAX_COOKIES_BYTES + 1)
        if not cookies_bytes:
            raise HTTPException(status_code=400, detail="Upload a Netscape-format cookies.txt file.")
        if len(cookies_bytes) > MAX_COOKIES_BYTES:
            raise HTTPException(status_code=400, detail="Cookies file is larger than 8 MB.")

    config = JobConfig(
        course_url=normalized.url,
        platform=normalized.platform,
        auth_method=auth_method,
        browser=browser if auth_method == "browser" else None,
        quality=quality,
        subtitles=subtitles,
        auto_subtitles=auto_subtitles,
        subtitle_languages=subtitle_languages,
        include_practice_tests=include_practice_tests if normalized.platform == "udemy" else False,
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
    return {
        "root": str(DOWNLOAD_DIR) if APP_ENV != "production" else "persistent-storage",
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
        if len(files) >= 1000:
            break
        rel = path.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
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
