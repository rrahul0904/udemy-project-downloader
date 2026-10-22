#!/usr/bin/env python3
"""Independently verify local Claude exports, bank provenance, and PDF integrity."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.claude_certification_batch import GROUPS, MANIFEST, OUTPUT, inspect_export, load_manifest


def pdf_pages(path: Path) -> int:
    if not path.is_file() or path.stat().st_size < 100:
        raise ValueError(f"Invalid PDF: {path}")
    with path.open("rb") as stream:
        header = stream.read(4)
    if header != b"%PDF":
        raise ValueError(f"Invalid PDF: {path}")
    result = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=True)
    match = re.search(r"^Pages:\s+(\d+)", result.stdout, re.MULTILINE)
    if not match or int(match.group(1)) < 1:
        raise ValueError(f"PDF has no readable pages: {path}")
    return int(match.group(1))


def git_value(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--render-samples", action="store_true")
    parser.add_argument("--tests", action="store_true")
    args = parser.parse_args()
    root = args.output.resolve()
    _, courses, manifest_sha = load_manifest(MANIFEST)
    ledger = json.loads((root / "progress.json").read_text())
    summary = json.loads((root / "summary.json").read_text())
    assert ledger["manifest_sha256"] == summary["manifest_sha256"] == manifest_sha
    assert len(ledger["courses"]) == len(courses) == 69
    assert all(r["export_state"] not in {"pending", "running"} for r in ledger["courses"].values())
    course_pdfs = 0
    quiz_pdfs = 0
    raw_questions = 0
    for course in courses:
        record = ledger["courses"][course["inventory_id"]]
        assert record["slug"] == course["slug"] and record["certification_code"] == course["certification_code"]
        if record["extracted_question_count"] == 0:
            continue
        path = ROOT / record["output_paths"]["json"]
        validated = inspect_export(path, course)
        assert validated["json_sha256"] == record["json_sha256"]
        assert validated["extracted_question_count"] == record["extracted_question_count"]
        assert validated["export_state"] == record["export_state"]
        pdf_pages(ROOT / record["output_paths"]["pdf"])
        course_pdfs += 1
        for pdf in record["output_paths"]["quiz_pdfs"]:
            pdf_pages(ROOT / pdf)
            quiz_pdfs += 1
        raw_questions += record["extracted_question_count"]
    groups = []
    distinct_total = 0
    for group in GROUPS:
        folder = root / group
        bank_path = folder / "question-bank.json"
        bank = json.loads(bank_path.read_text())
        group_summary = json.loads((folder / "summary.json").read_text())
        assert bank["certification_code"] == group
        assert bank["manifest_sha256"] == manifest_sha
        assert len(bank["questions"]) == group_summary["distinct_question_fingerprints"]
        assert len(bank["exams"]) == group_summary["exams_discovered"]
        assert sum(len(q["sources"]) for q in bank["questions"]) == group_summary["raw_question_instances"]
        assert len({q["fingerprint"] for q in bank["questions"]}) == len(bank["questions"])
        assert all(source["certification_code"] == group for q in bank["questions"] for source in q["sources"])
        assert (folder / "question-bank.html").read_text().lstrip().startswith("<!doctype html>")
        assert (folder / "question-bank.md").read_text().startswith("# ")
        assert isinstance(json.loads((folder / "duplicates.json").read_text()), list)
        pages = pdf_pages(folder / "question-bank.pdf")
        if args.render_samples:
            sample_dir = root / "verification-samples" / group
            sample_dir.mkdir(parents=True, exist_ok=True)
            for label, page in (("first", 1), ("middle", max(1, pages // 2))):
                subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-scale-to", "1200",
                                "-png", "-singlefile", str(folder / "question-bank.pdf"),
                                str(sample_dir / label)], check=True, capture_output=True)
        groups.append({**group_summary, "pdf_pages": pages,
                       "bank_json_sha256": hashlib.sha256(bank_path.read_bytes()).hexdigest()})
        distinct_total += len(bank["questions"])
    assert raw_questions == sum(g["raw_question_instances"] for g in groups)
    assert distinct_total == sum(g["distinct_question_fingerprints"] for g in groups)
    cross = json.loads((root / "cross-certification-duplicates.json").read_text())
    assert len(cross) == summary["cross_certification_duplicate_clusters"]
    assert not list(root.rglob("*cookies*.txt"))
    assert not git_value("ls-files", "downloads/claude-certifications")
    states = dict(Counter(r["export_state"] for r in ledger["courses"].values()))
    tests = None
    if args.tests:
        result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
                                cwd=ROOT, capture_output=True, text=True)
        match = re.search(r"Ran (\d+) tests", result.stderr)
        tests = {"command": "python -m unittest discover -s tests -q", "passed": result.returncode == 0,
                 "count": int(match.group(1)) if match else None}
        if result.returncode:
            raise RuntimeError("Automated test suite failed; inspect it separately")
    receipt = {"schema_version": "claude-extraction-verification/v1",
               "verified_at": datetime.now(timezone.utc).isoformat(), "manifest_sha256": manifest_sha,
               "repository_sha": git_value("rev-parse", "HEAD"),
               "working_tree_dirty": bool(git_value("status", "--porcelain", "--untracked-files=no")),
               "courses_in_manifest": 69, "course_states": states,
               "course_pdfs_checked": course_pdfs, "quiz_pdfs_checked": quiz_pdfs,
               "raw_question_instances": raw_questions, "sum_group_distinct_fingerprints": distinct_total,
               "cross_certification_duplicate_clusters": len(cross),
               "groups": groups, "tests": tests,
               "limits": ["Partial courses remain partial", "Physical device browser UI was not part of extraction",
                          "Source assessment correctness was not independently adjudicated"]}
    (root / "verification-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    lines = ["# Claude extraction verification", "", f"Verified: {receipt['verified_at']}", "",
             f"Manifest: 69 distinct courses; SHA-256 `{manifest_sha}`", "",
             f"States: {states}", "",
             f"PDFs checked: {course_pdfs} per-course, {quiz_pdfs} per-quiz, 6 certification-level.", "",
             f"Question instances: {raw_questions}. Group-level distinct fingerprints summed: {distinct_total}.", "",
             f"Cross-certification duplicate clusters: {len(cross)}; not merged.", "",
             f"Tests: {tests if tests is not None else 'not run by this receipt'}", "",
             f"Repository SHA: `{receipt['repository_sha']}`; dirty working tree: {receipt['working_tree_dirty']}.", "",
             "Partial courses and their reasons remain in `progress.json`. This receipt validates actual local exports, "
             "file counts, provenance, and PDF readability; it does not certify that third-party answers are factually correct.", ""]
    (root / "verification-report.md").write_text("\n".join(lines))
    print(f"VERIFIED: 69 courses, {raw_questions} question instances, {course_pdfs + quiz_pdfs + 6} PDFs checked", flush=True)


if __name__ == "__main__":
    main()
