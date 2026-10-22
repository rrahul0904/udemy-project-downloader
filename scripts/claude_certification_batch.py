#!/usr/bin/env python3
"""Run the authorized Mac practice exporter across the 69-course Claude manifest.

Question content and the progress ledger stay in gitignored downloads/. Browser
credentials live only in the host process's cookie jar; no cookies.txt is made.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.practice_tests import PracticeExportError, _session_from_cookiejar, export_practice_tests
from scripts.mac_practice_export import BROWSERS, _udemy_cookie_count
from yt_dlp.cookies import extract_cookies_from_browser

MANIFEST = ROOT / "docs/claude-certifications/cleaned_courses.json"
OUTPUT = ROOT / "downloads/claude-certifications"
GROUPS = ("CCAO-F", "CCDV-F", "CCAR-F", "CCAR-P", "ARCHITECT-VERIFY", "OTHER-CLAUDE")
EXPECTED = (25, 9, 17, 13, 4, 1)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_manifest(path: Path) -> tuple[dict, list[dict], str]:
    raw = path.read_bytes()
    manifest = json.loads(raw)
    groups = manifest["groups"]
    assert tuple(g["certification_code"] for g in groups) == GROUPS
    assert tuple(len(g["courses"]) for g in groups) == EXPECTED
    courses = [course for group in groups for course in group["courses"]]
    assert len(courses) == len({c["slug"] for c in courses}) == len({c["inventory_id"] for c in courses}) == 69
    assert sum(len(c["input_positions"]) for c in courses) == manifest["summary"]["submitted_links"] == 83
    assert len(manifest["removed_duplicate_occurrences"]) == 14
    for course in courses:
        assert course["url"] == f"https://www.udemy.com/course/{course['slug']}/"
        assert course["inventory_id"].startswith(course["certification_code"] + "-")
    return manifest, courses, hashlib.sha256(raw).hexdigest()


def initial_record(course: dict) -> dict:
    return {
        "inventory_id": course["inventory_id"],
        "certification_code": course["certification_code"],
        "slug": course["slug"],
        "canonical_url": course["url"],
        "source_batch": "added" if course.get("source_batch") else "original",
        "actual_title": None,
        "course_id": None,
        "access_status": "unchecked",
        "discovered_quiz_ids": [],
        "expected_question_count": None,
        "extracted_question_count": 0,
        "questions_with_choices": 0,
        "questions_with_correct_answers": 0,
        "questions_with_explanations": 0,
        "export_state": "pending",
        "warnings": [],
        "output_paths": {},
        "evidence_timestamp": None,
        "json_sha256": None,
    }


def load_ledger(path: Path, courses: list[dict], manifest_sha: str) -> dict:
    if path.exists():
        ledger = json.loads(path.read_text())
        if ledger.get("manifest_sha256") != manifest_sha:
            raise ValueError("Manifest changed; review course identity before resuming the ledger.")
        assert set(ledger["courses"]) == {c["inventory_id"] for c in courses}
        return ledger
    return {
        "schema_version": "claude-certification-batch/v1",
        "manifest_sha256": manifest_sha,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "courses": {c["inventory_id"]: initial_record(c) for c in courses},
    }


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    temp.replace(path)


def save_ledger(ledger: dict, path: Path) -> None:
    ledger["updated_at"] = utc_now()
    atomic_json(path, ledger)
    lines = ["# Claude certification extraction progress", "", f"Updated: {ledger['updated_at']}", "",
             "This ledger records authorized local exports. Pending and failed rows are not extracted question banks.", ""]
    for group in GROUPS:
        records = [r for r in ledger["courses"].values() if r["certification_code"] == group]
        lines.extend([f"## {group}", "", "| ID | Course | State | Quizzes | Questions | Expected |",
                      "| --- | --- | --- | ---: | ---: | ---: |"])
        for r in records:
            lines.append(f"| {r['inventory_id']} | {r['slug']} | {r['export_state']} | "
                         f"{len(r['discovered_quiz_ids'])} | {r['extracted_question_count']} | "
                         f"{r['expected_question_count'] if r['expected_question_count'] is not None else '?'} |")
        lines.append("")
    path.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")


def inspect_export(path: Path, course: dict) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if f"/course/{course['slug']}/" not in str(data.get("course_url") or ""):
        raise ValueError("Export URL does not match inventory slug")
    tests = data.get("practice_tests") or []
    actual = sum(len(t.get("assessments") or []) for t in tests)
    validation = data.get("validation") or {}
    if actual != validation.get("questions_retrieved"):
        raise ValueError("Question count disagrees with export validation")
    if len(tests) != validation.get("practice_sets_discovered"):
        raise ValueError("Quiz count disagrees with export validation")
    pdf = path.with_suffix(".pdf")
    html = path.with_suffix(".html")
    markdown = path.with_suffix(".md")
    report = path.with_name(path.stem + "-verification-report.md")
    set_pdfs = [p for p in path.parent.glob("*.pdf") if p != pdf]
    if not all(p.is_file() and p.stat().st_size > 100 for p in (pdf, html, markdown, report)):
        raise ValueError("A required output is missing or empty")
    if len(set_pdfs) != len(tests):
        raise ValueError("Per-quiz PDF count disagrees with discovered quiz count")
    status = validation.get("status")
    if actual and status == "succeeded" and all(
        validation.get(key) == actual for key in (
            "questions_with_answer_choices", "questions_with_correct_answers", "questions_with_explanations"
        )
    ):
        state = "complete"
    elif actual:
        state = "partial"
    elif status == "not_accessible":
        state = "not_accessible"
    elif status == "no_practice_tests":
        state = "no_quizzes"
    else:
        state = "failed"
    warnings = [str(w) for w in data.get("warnings") or []]
    if any("HTTP 429" in w for w in warnings):
        state = "rate_limited"
    return {
        "actual_title": data.get("course_title"),
        "course_id": str(data["course_id"]) if data.get("course_id") else None,
        "access_status": "accessible" if actual else ("not_accessible" if state == "not_accessible" else "unknown"),
        "discovered_quiz_ids": [str(t.get("id")) for t in tests if t.get("id") is not None],
        "expected_question_count": validation.get("questions_expected"),
        "extracted_question_count": actual,
        "questions_with_choices": validation.get("questions_with_answer_choices", 0),
        "questions_with_correct_answers": validation.get("questions_with_correct_answers", 0),
        "questions_with_explanations": validation.get("questions_with_explanations", 0),
        "export_state": state,
        "warnings": warnings,
        "output_paths": {"json": str(path.relative_to(ROOT)), "pdf": str(pdf.relative_to(ROOT)),
                         "html": str(html.relative_to(ROOT)), "markdown": str(markdown.relative_to(ROOT)),
                         "verification_report": str(report.relative_to(ROOT)),
                         "quiz_pdfs": [str(p.relative_to(ROOT)) for p in sorted(set_pdfs)]},
        "evidence_timestamp": data.get("exported_at"),
        "json_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def scan_existing(ledger: dict, courses: list[dict], output: Path) -> None:
    for course in courses:
        record = ledger["courses"][course["inventory_id"]]
        if record["export_state"] == "complete":
            try:
                path = ROOT / record["output_paths"]["json"]
                checked = inspect_export(path, course)
                if checked["json_sha256"] != record["json_sha256"] or checked["export_state"] != "complete":
                    raise ValueError("Prior complete export changed")
                record.update(checked)
                continue
            except (ValueError, OSError, KeyError, json.JSONDecodeError):
                record.update(export_state="pending", warnings=["Prior complete export could not be revalidated"],
                              output_paths={}, json_sha256=None)
        folder = output / course["certification_code"]
        candidates = sorted(folder.glob(f"{course['slug']}*/**/*practice-tests.json"),
                            key=lambda p: p.stat().st_mtime, reverse=True)
        for path in candidates:
            try:
                record.update(inspect_export(path, course))
                break
            except (ValueError, OSError, KeyError, json.JSONDecodeError):
                continue


def run() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--browser", choices=BROWSERS, default="chrome")
    parser.add_argument("--group", choices=GROUPS)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--scan-only", action="store_true")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    manifest, courses, sha = load_manifest(args.manifest)
    output = args.output.resolve()
    ledger_path = output / "progress.json"
    ledger = load_ledger(ledger_path, courses, sha)
    scan_existing(ledger, courses, output)
    save_ledger(ledger, ledger_path)
    print(f"Manifest: {len(courses)} courses, sha256 {sha}; ledger: {ledger_path}", flush=True)
    if args.scan_only:
        return 0
    try:
        jar = extract_cookies_from_browser(args.browser)
    except Exception as exc:
        print(f"Cannot read local {args.browser} session ({type(exc).__name__}); no export attempted.", file=sys.stderr)
        return 2
    if not _udemy_cookie_count(jar):
        print(f"No Udemy session in local {args.browser}; no export attempted.", file=sys.stderr)
        return 2
    selected = [c for c in courses if (not args.group or c["certification_code"] == args.group)]
    attempted = 0
    session = _session_from_cookiejar(jar, selected[0]["url"])
    try:
        for course in selected:
            record = ledger["courses"][course["inventory_id"]]
            if record["export_state"] == "complete":
                print(f"SKIP {course['inventory_id']} complete", flush=True)
                continue
            if args.limit is not None and attempted >= args.limit:
                break
            attempted += 1
            record.update(export_state="running", evidence_timestamp=utc_now())
            save_ledger(ledger, ledger_path)
            session.headers["Referer"] = course["url"]
            destination = output / course["certification_code"] / course["slug"] / "_practice-tests"
            try:
                result = export_practice_tests(course["url"], None, destination, session=session)
                record.update(inspect_export(result.output_json, course))
            except PracticeExportError as exc:
                record.update(export_state="failed", warnings=[str(exc)], evidence_timestamp=utc_now())
            except Exception as exc:
                record.update(export_state="failed", warnings=[f"{type(exc).__name__}: review local diagnostic files"],
                              evidence_timestamp=utc_now())
            save_ledger(ledger, ledger_path)
            print(f"{course['inventory_id']} {record['export_state']} "
                  f"quizzes={len(record['discovered_quiz_ids'])} questions={record['extracted_question_count']}", flush=True)
            if record["export_state"] == "rate_limited":
                print("Rate limit encountered; stopping the batch.", file=sys.stderr)
                return 3
            if args.delay > 0:
                time.sleep(args.delay)
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
