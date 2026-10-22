#!/usr/bin/env python3
"""Export authorized Udemy practice exams using the Mac's existing browser login.

Run on the Mac HOST (not inside Docker); no cookies.txt is created or uploaded.
The results are written directly to the repository's Docker bind-mounted
'downloads' directory and can be opened in the Course Intelligence Files UI.
Udemy login/enrollment remains required; no CAPTCHA/DRM bypass is attempted.
"""
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.practice_tests import (  # noqa: E402
    PracticeExportError,
    _session_from_cookiejar,
    export_practice_tests,
)
from app.safety import UrlValidationError, normalize_udemy_url, slug_from_url  # noqa: E402
from yt_dlp.cookies import extract_cookies_from_browser  # noqa: E402


BROWSERS = ("chrome", "safari", "firefox", "brave", "edge", "chromium", "vivaldi", "opera")


def _udemy_cookie_count(jar) -> int:
    """Count site cookies without printing names, values, or account details."""
    count = 0
    for cookie in jar:
        domain = str(getattr(cookie, "domain", "")).lower().lstrip(".")
        if domain == "udemy.com" or domain.endswith(".udemy.com"):
            count += 1
    return count


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export your accessible Udemy quiz without a cookies.txt upload."
    )
    parser.add_argument("url", help="Specific Udemy course or /learn/quiz/<id> URL")
    parser.add_argument("--browser", choices=BROWSERS, default="chrome",
                        help="Browser containing your signed-in Udemy session (default: chrome)")
    parser.add_argument("--downloads-dir", type=Path, default=ROOT / "downloads",
                        help="Host download folder bind-mounted into Docker (default: repo/downloads)")
    args = parser.parse_args(argv)

    try:
        course_url = normalize_udemy_url(args.url)
    except UrlValidationError as exc:
        print(f"Invalid Udemy URL: {exc}", file=sys.stderr)
        return 2

    print(f"Reading authorized Udemy browser session from local {args.browser}.")
    try:
        jar = extract_cookies_from_browser(args.browser)
    except Exception as exc:
        # Library failures vary by browser and macOS Keychain permissions.
        # Never print cookie values or upload the browser database.
        print(f"Could not read {args.browser} browser credentials: {type(exc).__name__}. "
              "Confirm the browser profile and macOS permission prompts.", file=sys.stderr)
        return 2

    if not _udemy_cookie_count(jar):
        print(
            f"No Udemy site cookies found in {args.browser}. Sign in to Udemy in that "
            "browser, confirm the practice test opens, and retry.",
            file=sys.stderr,
        )
        return 2

    # Generated artifacts are stored in the same host directory that the Docker
    # app mounts at /downloads; browser session tokens remain in host process
    # memory and do not cross the container boundary.
    download_root = args.downloads_dir.expanduser().resolve()
    relative_name = f"{slug_from_url(course_url)}-{uuid.uuid4().hex[:8]}"
    output_dir = download_root / relative_name / "_practice-tests"
    print("Exporting accessible quiz data locally (no cookie file, no cookie upload).")

    session = _session_from_cookiejar(jar, course_url)
    try:
        try:
            result = export_practice_tests(
                course_url, None, output_dir, session=session
            )
        except PracticeExportError as exc:
            print(f"Export was not accessible: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"Export failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
    finally:
        session.close()

    print(f"Practice exams found: {result.item_count}")
    print(f"Questions retrieved: {result.assessment_count}")
    print(f"Diagnostic HTML: {result.output_html}")
    for warning in result.warnings:
        print(f"Warning: {warning}")

    if result.assessment_count == 0:
        print("FAILED: No questions retrieved. The generated files are diagnostics, "
              "not a successful export.", file=sys.stderr)
        return 1

    if any(" but exported " in warning and " expected " in warning for warning in result.warnings):
        print("INCOMPLETE: Expected and retrieved question counts disagree. "
              "Inspect warnings before relying on the exported exam.", file=sys.stderr)
        return 1

    print(f"Exported PDF: {result.output_pdf}")
    if any("not found in the accessible curriculum" in warning for warning in result.warnings):
        print("Note: The direct quiz was attempted without the full curriculum. "
              "This run does not prove that every exam in the course was retrieved.")
    print("DONE: Local files are available under downloads/ and via the Docker Files view.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
