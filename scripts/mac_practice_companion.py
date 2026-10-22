#!/usr/bin/env python3
"""Loopback companion for one-click authorized Mac browser practice exports.

Run on the Mac host. Authentication cookies stay in this process's memory and
are never returned to the app or written to disk.
"""
from __future__ import annotations

import json
import secrets
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.mac_practice_export import BROWSERS, _udemy_cookie_count
from app.practice_tests import PracticeExportError, _session_from_cookiejar, export_practice_tests
from app.safety import UrlValidationError, normalize_udemy_url, slug_from_url
from yt_dlp.cookies import extract_cookies_from_browser

DOWNLOADS = ROOT / "downloads"
HOST = "127.0.0.1"
PORT = 8765
APP_ORIGINS = {"http://127.0.0.1:8080", "http://localhost:8080"}
TOKEN = secrets.token_urlsafe(32)
JOBS: dict[str, dict] = {}
LOCK = threading.Lock()


def allowed_origin(origin: str) -> bool:
    return origin in APP_ORIGINS


def valid_pairing(origin: str, token: str) -> bool:
    return allowed_origin(origin) and secrets.compare_digest(token, TOKEN)


def _export(job_id: str, url: str, browser: str) -> None:
    session = None
    try:
        jar = extract_cookies_from_browser(browser)
        if not _udemy_cookie_count(jar):
            raise RuntimeError(f"No Udemy cookies found in {browser}. Sign in and open the quiz, then retry.")
        session = _session_from_cookiejar(jar, url)
        output = DOWNLOADS / f"{slug_from_url(url)}-{job_id[:8]}" / "_practice-tests"
        result = export_practice_tests(url, None, output, session=session)
        if result.assessment_count == 0:
            state = "not_accessible" if result.validation.get("status") == "not_accessible" else "failed"
        elif result.validation.get("status") == "partial":
            state = "partial"
        else:
            state = "succeeded"
        with LOCK:
            JOBS[job_id].update({
                "status": state,
                "course_title": result.course_title,
                "exam_count": result.item_count,
                "question_count": result.assessment_count,
                "validation": result.validation,
                "warnings": result.warnings,
                "files": [str(path.relative_to(DOWNLOADS)) for path in
                          (result.output_pdf, *result.output_set_pdfs, result.output_json,
                           result.output_html, result.output_markdown, result.output_verification_report)
                          if path and path.is_file()],
            })
    except PracticeExportError as exc:
        _finish_error(job_id, "not_accessible", str(exc))
    except (UrlValidationError, RuntimeError, OSError, ValueError) as exc:
        _finish_error(job_id, "failed", str(exc))
    except Exception as exc:
        # Never surface browser/cookie values or arbitrary exception details.
        _finish_error(job_id, "failed", f"Local export failed ({type(exc).__name__}). Check browser permission and retry.")
    finally:
        if session:
            session.close()


def _finish_error(job_id: str, status: str, message: str) -> None:
    with LOCK:
        if job_id in JOBS:
            JOBS[job_id].update({"status": status, "error": message})


class Handler(BaseHTTPRequestHandler):
    server_version = "CoursePracticeCompanion/1"

    def log_message(self, fmt, *args):  # keep URLs and request data out of logs
        return

    def _json(self, status: int, body: dict, *, cors: bool = False) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if cors:
            self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", ""))
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(payload)

    def _origin_ok(self) -> bool:
        return allowed_origin(self.headers.get("Origin", ""))

    def _authorized(self) -> bool:
        return valid_pairing(self.headers.get("Origin", ""), self.headers.get("X-Companion-Token", ""))

    def do_OPTIONS(self):
        if not self._origin_ok():
            self.send_error(403)
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Companion-Token")
        self.send_header("Access-Control-Max-Age", "300")
        self.send_header("Vary", "Origin")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/pair":
            body = f"""<!doctype html><meta charset=utf-8><title>Pair Course Intelligence</title>
            <p id=s>Pairing with the local Course Intelligence app…</p><script>
            const allowed={json.dumps(sorted(APP_ORIGINS))};
            let origin=''; try {{ origin=window.opener && window.opener.location.origin; }} catch {{}}
            if (window.opener && allowed.includes(origin)) {{
              window.opener.postMessage({{type:'course-practice-pair', token:{json.dumps(TOKEN)}}}, origin);
              document.querySelector('#s').textContent='Paired. You can close this tab.';
            }} else document.querySelector('#s').textContent='Open this page from the local Course Intelligence app.';
            </script>""".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/health":
            if not self._origin_ok():
                self.send_error(403)
                return
            self._json(200, {"status": "ready"}, cors=True)
            return
        if path.startswith("/api/jobs/"):
            if not self._authorized():
                self.send_error(403)
                return
            job_id = path.rsplit("/", 1)[-1]
            with LOCK:
                job = JOBS.get(job_id)
                if job:
                    job = dict(job)
            if not job:
                self._json(404, {"error": "Export job not found."}, cors=True)
            else:
                self._json(200, job, cors=True)
            return
        self.send_error(404)

    def do_POST(self):
        if urlparse(self.path).path != "/api/exports":
            self.send_error(404)
            return
        if not self._authorized():
            self.send_error(403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= 8192:
                raise ValueError
            data = json.loads(self.rfile.read(length))
            url = normalize_udemy_url(str(data.get("url", ""))).url
            browser = str(data.get("browser", "chrome"))
            if browser not in BROWSERS:
                raise ValueError
        except (ValueError, TypeError, json.JSONDecodeError, UrlValidationError):
            self._json(400, {"error": "Provide a valid Udemy URL and supported browser."}, cors=True)
            return
        job_id = uuid.uuid4().hex
        with LOCK:
            JOBS[job_id] = {"id": job_id, "status": "running", "course_title": None,
                            "exam_count": 0, "question_count": 0, "files": [], "warnings": []}
        threading.Thread(target=_export, args=(job_id, url, browser), daemon=True).start()
        self._json(202, {"id": job_id, "status": "running"}, cors=True)


def main() -> None:
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Mac practice companion listening at http://{HOST}:{PORT} (Ctrl-C to stop).")
    print("Cookies remain in this process's memory; no cookie file or upload is used.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping local practice companion.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
