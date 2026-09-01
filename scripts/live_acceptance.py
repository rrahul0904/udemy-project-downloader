#!/usr/bin/env python3
"""Production acceptance checks for the deployed Course Intelligence service.

This runner deliberately uses only the Python standard library so it can be
executed from CI, a developer workstation, or a minimal operations shell.
Secrets are read from environment variables/arguments and are never printed.

Core smoke checks run without downloading anything. A real downloader flow is
opt-in and requires an explicitly authorized YouTube URL.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


TERMINAL_JOB_STATES = {"succeeded", "failed", "cancelled"}
SECURITY_HEADERS = (
    "content-security-policy",
    "x-content-type-options",
    "referrer-policy",
    "x-frame-options",
)


class AcceptanceError(RuntimeError):
    pass


def normalize_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise AcceptanceError("PRODUCTION_URL must be an absolute HTTPS URL.")
    if parsed.username or parsed.password:
        raise AcceptanceError("PRODUCTION_URL must not contain credentials.")
    return value


def basic_auth_header(username: str, password: str) -> str:
    if not username or not password:
        raise AcceptanceError("Production username/password are required.")
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        try:
            return json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AcceptanceError(f"Expected JSON response, got {self.body[:200]!r}") from exc


class Client:
    def __init__(self, base_url: str, username: str, password: str, timeout: int = 30):
        self.base_url = normalize_base_url(base_url)
        self.auth = basic_auth_header(username, password)
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = True,
        form: dict[str, Any] | None = None,
        json_payload: dict[str, Any] | None = None,
        origin: str | None = None,
    ) -> Response:
        if not path.startswith("/"):
            raise AcceptanceError(f"Path must start with '/': {path}")
        headers = {
            "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
            "User-Agent": "course-intelligence-production-acceptance/1",
        }
        if authenticated:
            headers["Authorization"] = self.auth
        if origin:
            headers["Origin"] = origin
        data: bytes | None = None
        if form is not None and json_payload is not None:
            raise AcceptanceError("Use either form or json_payload, not both.")
        if form is not None:
            data = urlencode({k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in form.items()}).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif json_payload is not None:
            data = json.dumps(json_payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(self.base_url + path, data=data, headers=headers, method=method.upper())
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return Response(
                    response.status,
                    {key.lower(): value for key, value in response.headers.items()},
                    response.read(),
                )
        except HTTPError as exc:
            return Response(
                exc.code,
                {key.lower(): value for key, value in exc.headers.items()},
                exc.read(),
            )
        except URLError as exc:
            raise AcceptanceError(f"Unable to reach production service: {exc.reason}") from exc


def require_status(response: Response, expected: int | set[int], label: str) -> None:
    allowed = {expected} if isinstance(expected, int) else expected
    if response.status not in allowed:
        body = response.body.decode("utf-8", errors="replace")[:500]
        raise AcceptanceError(f"{label}: expected HTTP {sorted(allowed)}, got {response.status}: {body}")


def require_security_headers(response: Response, label: str) -> None:
    missing = [name for name in SECURITY_HEADERS if not response.headers.get(name)]
    if missing:
        raise AcceptanceError(f"{label}: missing security headers: {', '.join(missing)}")


def flatten_lessons(library: dict[str, Any]) -> list[dict[str, Any]]:
    lessons: list[dict[str, Any]] = []
    for course in library.get("courses", []):
        if not isinstance(course, dict):
            continue
        for lesson in course.get("lessons", []):
            if isinstance(lesson, dict):
                item = dict(lesson)
                item["course_id"] = course.get("id")
                item["course_title"] = course.get("title")
                lessons.append(item)
    return lessons


def run_core_checks(client: Client) -> dict[str, Any]:
    health = client.request("GET", "/api/health", authenticated=False)
    require_status(health, 200, "public health")
    if health.json().get("status") != "ok":
        raise AcceptanceError("public health: expected status=ok")
    require_security_headers(health, "public health")

    for path in ("/", "/learn", "/lab", "/api/readiness", "/api/jobs"):
        response = client.request("GET", path, authenticated=False)
        require_status(response, 401, f"anonymous protection {path}")
        if "basic" not in response.headers.get("www-authenticate", "").lower():
            raise AcceptanceError(f"anonymous protection {path}: Basic auth challenge missing")

    anon_create = client.request(
        "POST",
        "/api/jobs",
        authenticated=False,
        form={"course_url": "https://www.youtube.com/watch?v=AAAAAAAAAAA", "confirm_authorized": True},
    )
    require_status(anon_create, 401, "anonymous job creation")

    page_results: dict[str, int] = {}
    for path in ("/", "/learn", "/lab"):
        response = client.request("GET", path)
        require_status(response, 200, f"authenticated route {path}")
        require_security_headers(response, f"authenticated route {path}")
        page_results[path] = response.status

    readiness = client.request("GET", "/api/readiness")
    require_status(readiness, 200, "readiness")
    ready = readiness.json()
    if ready.get("status") != "ready":
        raise AcceptanceError(f"readiness: unexpected payload: {ready}")
    checks = ready.get("checks") or {}
    for key in ("database", "data_dir", "download_dir", "ffmpeg", "yt_dlp"):
        if key not in checks:
            raise AcceptanceError(f"readiness: missing check {key}")
    if checks.get("database") != "ok" or not all(bool(checks.get(k)) for k in ("data_dir", "download_dir", "ffmpeg", "yt_dlp")):
        raise AcceptanceError(f"readiness: one or more runtime dependencies are not ready: {checks}")

    library_response = client.request("GET", "/api/library")
    require_status(library_response, 200, "course library")
    library = library_response.json()

    traversal = client.request("GET", "/files/%2e%2e/%2e%2e/etc/passwd")
    require_status(traversal, {400, 404}, "path traversal")

    unsupported = client.request(
        "POST",
        "/api/jobs",
        form={"course_url": "https://example.com/not-supported", "confirm_authorized": True},
        origin=client.base_url,
    )
    require_status(unsupported, 400, "unsupported downloader source")

    cross_origin = client.request(
        "POST",
        "/api/jobs",
        form={"course_url": "https://www.youtube.com/watch?v=AAAAAAAAAAA", "confirm_authorized": True},
        origin="https://invalid-origin.example",
    )
    require_status(cross_origin, 403, "cross-origin mutation rejection")

    return {
        "health": "pass",
        "readiness": ready,
        "authenticated_routes": page_results,
        "course_count": library.get("course_count", 0),
        "lesson_count": library.get("lesson_count", 0),
        "security": "pass",
    }


def create_download_job(client: Client, url: str) -> dict[str, Any]:
    response = client.request(
        "POST",
        "/api/jobs",
        form={
            "course_url": url,
            "auth_method": "none",
            "quality": "360",
            "subtitles": True,
            "auto_subtitles": True,
            "subtitle_languages": "en.*",
            "include_practice_tests": False,
            "confirm_authorized": True,
        },
        origin=client.base_url,
    )
    require_status(response, 200, "authorized download job creation")
    payload = response.json()
    if not payload.get("id"):
        raise AcceptanceError("authorized download job creation: missing job id")
    return payload


def wait_for_job(client: Client, job_id: str, timeout: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.request("GET", f"/api/jobs/{job_id}")
        require_status(response, 200, f"job polling {job_id}")
        last = response.json()
        if last.get("status") in TERMINAL_JOB_STATES:
            return last
        time.sleep(2)
    raise AcceptanceError(f"Job {job_id} did not reach a terminal state within {timeout}s; last={last.get('status')}")


def find_download_lesson(client: Client, job_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    short_id = job_id[:8]
    downloads = client.request("GET", "/api/downloads")
    require_status(downloads, 200, "download inventory")
    download_payload = downloads.json()
    paths = [item.get("path", "") for item in download_payload.get("files", []) if isinstance(item, dict)]
    if not any(short_id in path for path in paths):
        raise AcceptanceError("Completed job output was not found in persistent download inventory.")

    library_response = client.request("GET", "/api/library")
    require_status(library_response, 200, "course library after download")
    library = library_response.json()
    lessons = flatten_lessons(library)
    matching = [lesson for lesson in lessons if short_id in str(lesson.get("transcript_path", "")) or short_id in str(lesson.get("media_path", ""))]
    if not matching:
        raise AcceptanceError(
            "The authorized test download completed but did not yield a transcript-bearing lesson. "
            "Use an authorized YouTube test URL with English captions/transcript."
        )
    return matching[0], download_payload


def run_download_acceptance(client: Client, url: str, timeout: int, state_path: Path | None) -> dict[str, Any]:
    job = create_download_job(client, url)
    job_id = str(job["id"])
    finished = wait_for_job(client, job_id, timeout)
    if finished.get("status") != "succeeded":
        logs = finished.get("logs") or []
        tail = [str(line)[:300] for line in logs[-5:]]
        raise AcceptanceError(f"Authorized download failed: status={finished.get('status')}, log_tail={tail}")

    lesson, _ = find_download_lesson(client, job_id)
    lesson_id = str(lesson["id"])
    transcript_path = str(lesson["transcript_path"])
    transcript_query = urlencode({"path": transcript_path})
    transcript_response = client.request("GET", f"/api/learning/transcript?{transcript_query}")
    require_status(transcript_response, 200, "transcript retrieval")
    transcript = transcript_response.json()
    segments = transcript.get("segments") or []
    if not segments:
        raise AcceptanceError("Transcript has no segments; cannot complete persistence acceptance.")
    segment = segments[0]
    marker = f"production-acceptance:{job_id}"

    note = client.request(
        "PUT",
        f"/api/learning/lessons/{lesson_id}/notes",
        json_payload={"body": marker},
        origin=client.base_url,
    )
    require_status(note, 200, "note persistence write")
    if note.json().get("body") != marker:
        raise AcceptanceError("note persistence write: marker was not returned")

    bookmark_text = str(segment.get("text") or marker)[:4000]
    bookmark = client.request(
        "POST",
        f"/api/learning/lessons/{lesson_id}/bookmarks",
        json_payload={
            "segment_index": 0,
            "start_ms": segment.get("start"),
            "end_ms": segment.get("end"),
            "text": bookmark_text,
        },
        origin=client.base_url,
    )
    require_status(bookmark, 200, "bookmark persistence write")
    bookmark_payload = bookmark.json()

    search_words = [word.strip(".,!?;:()[]{}\"'") for word in bookmark_text.split()]
    search_term = next((word for word in search_words if len(word) >= 4 and word.isalnum()), "")
    if not search_term:
        raise AcceptanceError("Could not derive a safe transcript search term from the downloaded lesson.")
    search_query = urlencode({"q": search_term, "lesson_id": lesson_id, "limit": 10})
    search_response = client.request("GET", f"/api/learning/search?{search_query}")
    require_status(search_response, 200, "lesson FTS search")
    if not search_response.json().get("hits"):
        raise AcceptanceError("FTS search did not return a hit for the downloaded transcript.")

    state = {
        "job_id": job_id,
        "lesson_id": lesson_id,
        "transcript_path": transcript_path,
        "note_marker": marker,
        "bookmark_id": bookmark_payload.get("id"),
        "search_term": search_term,
    }
    if state_path:
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def run_cancellation_acceptance(client: Client, url: str, timeout: int) -> dict[str, Any]:
    job = create_download_job(client, url)
    job_id = str(job["id"])
    deadline = time.monotonic() + min(timeout, 60)
    current = job
    while time.monotonic() < deadline:
        response = client.request("GET", f"/api/jobs/{job_id}")
        require_status(response, 200, "cancellation polling")
        current = response.json()
        status = current.get("status")
        if status in {"queued", "running"}:
            cancel = client.request("DELETE", f"/api/jobs/{job_id}", origin=client.base_url)
            require_status(cancel, 200, "job cancellation")
            final = client.request("GET", f"/api/jobs/{job_id}")
            require_status(final, 200, "cancelled job verification")
            final_payload = final.json()
            if final_payload.get("status") != "cancelled":
                raise AcceptanceError(f"Job cancellation did not persist cancelled state: {final_payload.get('status')}")
            return {"job_id": job_id, "status": "cancelled"}
        if status in TERMINAL_JOB_STATES:
            raise AcceptanceError(
                "Cancellation test job reached a terminal state before cancellation. "
                "Provide a slower authorized test URL for PRODUCTION_CANCEL_TEST_URL."
            )
        time.sleep(1)
    raise AcceptanceError("Cancellation test job never became queued/running.")


def verify_persisted_state(client: Client, state_path: Path) -> dict[str, Any]:
    if not state_path.is_file():
        raise AcceptanceError(f"Persistence state file not found: {state_path}")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    job_id = str(state["job_id"])
    lesson_id = str(state["lesson_id"])
    marker = str(state["note_marker"])
    bookmark_id = str(state["bookmark_id"])
    search_term = str(state["search_term"])

    jobs = client.request("GET", "/api/jobs")
    require_status(jobs, 200, "persisted job history")
    if not any(str(item.get("id")) == job_id for item in jobs.json().get("jobs", [])):
        raise AcceptanceError("Persisted job history no longer contains the acceptance job.")

    find_download_lesson(client, job_id)

    note = client.request("GET", f"/api/learning/lessons/{lesson_id}/notes")
    require_status(note, 200, "persisted note")
    if note.json().get("body") != marker:
        raise AcceptanceError("Persisted note marker was lost or changed.")

    bookmarks = client.request("GET", f"/api/learning/lessons/{lesson_id}/bookmarks")
    require_status(bookmarks, 200, "persisted bookmarks")
    if not any(str(item.get("id")) == bookmark_id for item in bookmarks.json().get("bookmarks", [])):
        raise AcceptanceError("Persisted acceptance bookmark was lost.")

    search_query = urlencode({"q": search_term, "lesson_id": lesson_id, "limit": 10})
    search = client.request("GET", f"/api/learning/search?{search_query}")
    require_status(search, 200, "persisted FTS search")
    if not search.json().get("hits"):
        raise AcceptanceError("Persisted transcript FTS index no longer returns the acceptance search hit.")

    return {"job_id": job_id, "lesson_id": lesson_id, "persistence": "pass"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the live Course Intelligence production deployment.")
    parser.add_argument("--url", default=os.getenv("PRODUCTION_URL", ""))
    parser.add_argument("--username", default=os.getenv("PRODUCTION_APP_USER", "admin"))
    parser.add_argument("--password", default=os.getenv("PRODUCTION_APP_PASSWORD", ""))
    parser.add_argument("--authorized-test-url", default=os.getenv("PRODUCTION_AUTHORIZED_TEST_URL", ""))
    parser.add_argument("--cancel-test-url", default=os.getenv("PRODUCTION_CANCEL_TEST_URL", ""))
    parser.add_argument("--job-timeout", type=int, default=int(os.getenv("PRODUCTION_JOB_TIMEOUT", "900")))
    parser.add_argument("--state-file", default=os.getenv("PRODUCTION_ACCEPTANCE_STATE", "production-acceptance-state.json"))
    parser.add_argument("--verify-persistence", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.url:
        raise AcceptanceError("PRODUCTION_URL/--url is required.")
    client = Client(args.url, args.username, args.password)
    report: dict[str, Any] = {"production_url": normalize_base_url(args.url)}
    report["core"] = run_core_checks(client)

    state_path = Path(args.state_file)
    if args.verify_persistence:
        report["persistence"] = verify_persisted_state(client, state_path)
    else:
        if args.authorized_test_url:
            report["download"] = run_download_acceptance(client, args.authorized_test_url, args.job_timeout, state_path)
        if args.cancel_test_url:
            report["cancellation"] = run_cancellation_acceptance(client, args.cancel_test_url, args.job_timeout)

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AcceptanceError as exc:
        print(f"PRODUCTION ACCEPTANCE FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
