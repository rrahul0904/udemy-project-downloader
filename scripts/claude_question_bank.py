#!/usr/bin/env python3
"""Build private, provenance-preserving Claude certification question banks.

Only actual, validated local Udemy exports are included. This script never
contacts Udemy and never publishes source question text outside downloads/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from html import escape, unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.practice_tests import _assessment_answers, _assessment_explanation, _assessment_prompt
from scripts.claude_certification_batch import GROUPS, MANIFEST, OUTPUT, load_manifest


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def identity(stem: str, options: list[str]) -> tuple[str, str]:
    normalized_stem = normalize(stem)
    normalized_options = sorted(normalize(option) for option in options)
    encoded = json.dumps([normalized_stem, normalized_options], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest(), hashlib.sha256(normalized_stem.encode()).hexdigest()


def resolve_correct(correct: object, options: list[str]) -> list[str] | None:
    """Link returned answer keys to the source quiz's own option order."""
    if correct is None:
        return None
    values = correct if isinstance(correct, list) else [correct]
    resolved = []
    for value in values:
        if not isinstance(value, str):
            return None
        if len(value) == 1 and value.casefold() in "abcdefghijklmnopqrstuvwxyz":
            index = ord(value.casefold()) - ord("a")
            if index >= len(options):
                return None
            resolved.append(options[index])
        else:
            match = next((option for option in options if normalize(option) == normalize(value)), None)
            if match is None:
                return None
            resolved.append(match)
    return resolved or None


def source_label(source: dict) -> str:
    return f"{source['inventory_id']} / quiz {source['quiz_id']} / question {source['order']}"


def question_records(group: str, records: list[dict]) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    unique: dict[str, dict] = {}
    stem_groups: dict[str, set[str]] = defaultdict(set)
    exams: list[dict] = []
    courses: list[dict] = []
    for record in records:
        if not record["extracted_question_count"]:
            continue
        path = ROOT / record["output_paths"]["json"]
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != record["json_sha256"]:
            raise ValueError(f"Export changed after validation: {record['inventory_id']}")
        payload = json.loads(raw)
        if payload.get("course_id") != record["course_id"]:
            raise ValueError(f"Course identity changed: {record['inventory_id']}")
        courses.append({
            "inventory_id": record["inventory_id"], "slug": record["slug"],
            "course_id": record["course_id"], "title": record["actual_title"],
            "url": record["canonical_url"], "export_state": record["export_state"],
            "exported_at": record["evidence_timestamp"], "source_json_sha256": record["json_sha256"],
        })
        for test in payload.get("practice_tests") or []:
            quiz_id = str(test.get("id") or "unknown")
            questions = test.get("assessments") or []
            exams.append({"inventory_id": record["inventory_id"], "course_id": record["course_id"],
                          "quiz_id": quiz_id, "title": test.get("title"),
                          "expected_count": test.get("expected_assessment_count"), "retrieved_count": len(questions)})
            for order, assessment in enumerate(questions, 1):
                stem = unescape(_assessment_prompt(assessment))
                options = [unescape(option) for option in _assessment_answers(assessment)]
                if not stem:
                    raise ValueError(f"Missing stem in {record['inventory_id']} quiz {quiz_id} question {order}")
                fingerprint, stem_fingerprint = identity(stem, options)
                source = {"certification_code": group, "inventory_id": record["inventory_id"],
                          "course_id": record["course_id"], "quiz_id": quiz_id,
                          "question_id": assessment.get("id") or assessment.get("assessment_id"), "order": order}
                correct = assessment.get("correct_response") or assessment.get("correct_responses")
                explanation = unescape(_assessment_explanation(assessment)) or None
                variant = {"source": source, "correct_response": correct,
                           "resolved_correct_options": resolve_correct(correct, options), "explanation": explanation}
                if fingerprint not in unique:
                    unique[fingerprint] = {"fingerprint": fingerprint, "stem_fingerprint": stem_fingerprint,
                                           "stem": stem, "options": options, "sources": [], "answer_variants": []}
                unique[fingerprint]["sources"].append(source)
                unique[fingerprint]["answer_variants"].append(variant)
                stem_groups[stem_fingerprint].add(fingerprint)
    questions = list(unique.values())
    for question in questions:
        variants = question["answer_variants"]
        answer_keys = {json.dumps(sorted(normalize(o) for o in v["resolved_correct_options"]), ensure_ascii=False)
                       for v in variants if v["resolved_correct_options"] is not None}
        question["answer_conflict"] = len(answer_keys) > 1
        question["answer_linkage_unverified"] = any(v["correct_response"] is not None and
                                                     v["resolved_correct_options"] is None for v in variants)
        question["explanation_variants"] = len({normalize(v["explanation"] or "") for v in variants})
        question["duplicate_option_count"] = len(question["options"]) - len({normalize(o) for o in question["options"]})
    exact = [{"fingerprint": q["fingerprint"], "sources": q["sources"],
              "answer_conflict": q["answer_conflict"]} for q in questions if len(q["sources"]) > 1]
    potential = [{"stem_fingerprint": stem, "fingerprints": sorted(fingerprints)}
                 for stem, fingerprints in stem_groups.items() if len(fingerprints) > 1]
    return questions, courses, exams, exact + potential


def write_markdown(path: Path, group: str, questions: list[dict], courses: list[dict], exams: list[dict]) -> None:
    lines = [f"# {group} local question bank", "",
             f"{len(courses)} accessible source courses; {len(exams)} quiz records; {len(questions)} distinct question fingerprints.",
             "", "Question text is retained locally for authorized personal study. Source instances remain linked below.", ""]
    for course in courses:
        lines.append(f"- {course['inventory_id']}: {course['title']} — {course['url']} (course ID {course['course_id']})")
    lines.append("")
    for index, question in enumerate(questions, 1):
        lines.extend([f"## {index}. {question['stem']}", ""])
        lines.extend(f"- {chr(65 + i)}. {option}" for i, option in enumerate(question["options"]))
        lines.append("")
        first = next((v for v in question["answer_variants"] if v["resolved_correct_options"]),
                     question["answer_variants"][0])
        if first["resolved_correct_options"] and not question["answer_conflict"]:
            lines.extend([f"Correct response (source {source_label(first['source'])}): "
                          f"{'; '.join(first['resolved_correct_options'])}", ""])
        if first["explanation"] and not question["answer_conflict"]:
            lines.extend([f"Explanation: {first['explanation']}", ""])
        if question["answer_conflict"]:
            lines.extend(["**Answer conflict across sources; review the source exports.**", ""])
        if question["answer_linkage_unverified"]:
            lines.extend(["**Some source answer keys could not be linked to an option; review source exports.**", ""])
        if question["duplicate_option_count"]:
            lines.extend(["**Source question contains repeated answer options.**", ""])
        lines.extend(["Sources:", *[f"- {source_label(source)}" for source in question["sources"]], ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_html(path: Path, group: str, questions: list[dict], courses: list[dict]) -> None:
    sections = []
    for index, question in enumerate(questions, 1):
        options = "".join(f"<li>{chr(65 + i)}. {escape(option)}</li>" for i, option in enumerate(question["options"]))
        first = next((v for v in question["answer_variants"] if v["resolved_correct_options"]),
                     question["answer_variants"][0])
        correct = (f"<p><b>Correct:</b> {escape('; '.join(first['resolved_correct_options']))}</p>"
                   if first["resolved_correct_options"] and not question["answer_conflict"] else "")
        explanation = (f"<p><b>Explanation:</b> {escape(first['explanation'])}</p>"
                       if first["explanation"] and not question["answer_conflict"] else "")
        conflict = "<p class='alert'>Answer conflict across sources; review source exports.</p>" if question["answer_conflict"] else ""
        unverified = ("<p class='alert'>Some source answer keys could not be linked to an option.</p>"
                      if question["answer_linkage_unverified"] else "")
        repeated = ("<p class='alert'>Source question contains repeated answer options.</p>"
                    if question["duplicate_option_count"] else "")
        sources = "".join(f"<li>{escape(source_label(s))}</li>" for s in question["sources"])
        sections.append(f"<article><h2>{index}. {escape(question['stem'])}</h2><ol type='A'>{options}</ol>"
                        f"{correct}{explanation}{conflict}{unverified}{repeated}<details><summary>Provenance ({len(question['sources'])})</summary>"
                        f"<ul>{sources}</ul></details></article>")
    course_list = "".join(f"<li>{escape(c['inventory_id'])}: {escape(c['title'] or c['slug'])} "
                          f"(<a href='{escape(c['url'], quote=True)}'>course</a>)</li>" for c in courses)
    path.write_text(f"<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                    f"<title>{escape(group)} local question bank</title><style>body{{font:16px/1.55 system-ui;max-width:880px;margin:auto;padding:24px;background:#f5f4f0;color:#20302e}}"
                    "article,header{background:white;padding:22px;margin:16px 0;border:1px solid #ddd;border-radius:8px}"
                    "h2{font-size:1.15rem}li{margin:5px 0}.alert{color:#a43a25;font-weight:bold}details{margin-top:12px}</style>"
                    f"<header><h1>{escape(group)} local question bank</h1><p>{len(questions)} distinct question fingerprints."
                    " For authorized personal study; source instances are retained.</p><ul>"
                    f"{course_list}</ul></header>{''.join(sections)}</html>", encoding="utf-8")


def write_pdf(path: Path, group: str, questions: list[dict], courses: list[dict]) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    heading = ParagraphStyle("BankHeading", parent=styles["Heading1"], textColor=colors.HexColor("#173c42"), spaceAfter=14)
    question_style = ParagraphStyle("BankQuestion", parent=styles["Heading3"], fontSize=10.5, leading=14, spaceBefore=13)
    body = ParagraphStyle("BankBody", parent=styles["BodyText"], fontSize=9, leading=12, spaceAfter=5)
    source_style = ParagraphStyle("BankSource", parent=body, fontSize=7.5, leading=10, textColor=colors.HexColor("#52615f"))
    pdf_escape = lambda value: escape(value, quote=False)
    story = [Paragraph(pdf_escape(group) + " local question bank", heading),
             Paragraph(f"{len(courses)} source courses · {len(questions)} distinct question fingerprints", body),
             Paragraph("Authorized personal study. Each question retains its source instances.", body), Spacer(1, 8)]
    story.append(Paragraph("Source courses", question_style))
    for course in courses:
        story.append(Paragraph(pdf_escape(f"{course['inventory_id']}: {course['title'] or course['slug']} "
                                          f"(course ID {course['course_id']}; {course['url']})"), source_style))
    story.append(Spacer(1, 8))
    for index, question in enumerate(questions, 1):
        story.append(Paragraph(f"{index}. {pdf_escape(question['stem'])}", question_style))
        for option_index, option in enumerate(question["options"]):
            story.append(Paragraph(f"{chr(65 + option_index)}. {pdf_escape(option)}", body))
        first = next((v for v in question["answer_variants"] if v["resolved_correct_options"]),
                     question["answer_variants"][0])
        if first["resolved_correct_options"] and not question["answer_conflict"]:
            story.append(Paragraph("<b>Correct:</b> " + pdf_escape("; ".join(first["resolved_correct_options"])), body))
        if first["explanation"] and not question["answer_conflict"]:
            story.append(Paragraph("<b>Explanation:</b> " + pdf_escape(first["explanation"]), body))
        if question["answer_conflict"]:
            story.append(Paragraph("<b>Answer conflict across sources; review the source exports.</b>", body))
        if question["answer_linkage_unverified"]:
            story.append(Paragraph("<b>Some source answer keys could not be linked to an option.</b>", body))
        if question["duplicate_option_count"]:
            story.append(Paragraph("<b>Source question contains repeated answer options.</b>", body))
        story.append(Paragraph("Sources: " + pdf_escape("; ".join(source_label(s) for s in question["sources"])), source_style))
    def footer(canvas, doc):
        canvas.saveState(); canvas.setFont("Helvetica", 8); canvas.setFillColor(colors.grey)
        canvas.drawRightString(letter[0] - 40, 25, f"Page {doc.page}"); canvas.restoreState()
    SimpleDocTemplate(str(path), pagesize=letter, leftMargin=40, rightMargin=40,
                      topMargin=42, bottomMargin=45, title=f"{group} local question bank").build(
                          story, onFirstPage=footer, onLaterPages=footer)


def build_group(group: str, ledger: dict, root: Path) -> tuple[dict, dict]:
    records = [r for r in ledger["courses"].values() if r["certification_code"] == group]
    questions, courses, exams, duplicates = question_records(group, records)
    raw_count = sum(r["extracted_question_count"] for r in records)
    if raw_count != sum(len(q["sources"]) for q in questions):
        raise ValueError(f"Provenance count mismatch for {group}")
    group_dir = root / group
    group_dir.mkdir(parents=True, exist_ok=True)
    bank = {"schema_version": "claude-question-bank/v1", "certification_code": group,
            "manifest_sha256": ledger["manifest_sha256"], "generated_at": datetime.now(timezone.utc).isoformat(),
            "courses": courses, "exams": exams, "questions": questions}
    (group_dir / "question-bank.json").write_text(json.dumps(bank, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (group_dir / "duplicates.json").write_text(json.dumps(duplicates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if questions:
        write_markdown(group_dir / "question-bank.md", group, questions, courses, exams)
        write_html(group_dir / "question-bank.html", group, questions, courses)
        write_pdf(group_dir / "question-bank.pdf", group, questions, courses)
    summary = {"certification_code": group, "courses_in_inventory": len(records),
               "courses_complete": sum(r["export_state"] == "complete" for r in records),
               "courses_partial": sum(r["export_state"] == "partial" for r in records),
               "courses_no_quizzes": sum(r["export_state"] == "no_quizzes" for r in records),
               "courses_not_accessible": sum(r["export_state"] == "not_accessible" for r in records),
               "courses_failed": sum(r["export_state"] in {"failed", "rate_limited"} for r in records),
               "courses_pending": sum(r["export_state"] in {"pending", "running"} for r in records),
               "exams_discovered": len(exams), "raw_question_instances": raw_count,
               "distinct_question_fingerprints": len(questions),
               "exact_duplicate_clusters": sum(len(q["sources"]) > 1 for q in questions),
               "potential_duplicate_stem_clusters": sum("stem_fingerprint" in d for d in duplicates),
               "answer_conflicts": sum(q["answer_conflict"] for q in questions),
               "answer_linkage_unverified": sum(q["answer_linkage_unverified"] for q in questions),
               "questions_with_repeated_options": sum(bool(q["duplicate_option_count"]) for q in questions),
               "output_directory": str(group_dir.relative_to(ROOT))}
    (group_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary, {q["fingerprint"]: q["sources"] for q in questions}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--group", choices=GROUPS)
    args = parser.parse_args()
    root = args.output.resolve()
    _, _, sha = load_manifest(MANIFEST)
    ledger = json.loads((root / "progress.json").read_text())
    if ledger["manifest_sha256"] != sha:
        raise ValueError("Manifest and progress ledger SHA-256 differ")
    summaries = []
    global_sources: dict[str, list[dict]] = defaultdict(list)
    for group in (args.group,) if args.group else GROUPS:
        summary, registry = build_group(group, ledger, root)
        summaries.append(summary)
        for fingerprint, sources in registry.items():
            global_sources[fingerprint].extend(sources)
        print(f"{group}: {summary['raw_question_instances']} raw / {summary['distinct_question_fingerprints']} distinct", flush=True)
    if not args.group:
        cross_group = [{"fingerprint": fingerprint, "sources": sources}
                       for fingerprint, sources in global_sources.items()
                       if len({s["certification_code"] for s in sources}) > 1]
        (root / "cross-certification-duplicates.json").write_text(
            json.dumps(cross_group, ensure_ascii=False, indent=2) + "\n")
        batches = {name: sum(r["source_batch"] == name for r in ledger["courses"].values())
                   for name in ("original", "added")}
        aggregate = {"manifest_sha256": sha, "generated_at": datetime.now(timezone.utc).isoformat(),
                     "input_batches": batches, "groups": summaries,
                     "cross_certification_duplicate_clusters": len(cross_group)}
        (root / "summary.json").write_text(json.dumps(aggregate, indent=2) + "\n")
        lines = ["# Claude certification extraction summary", "", f"Generated: {aggregate['generated_at']}",
                 "", f"Manifest SHA-256: `{sha}`", "",
                 f"Input batches: {batches['original']} original + {batches['added']} added = 69 distinct courses.",
                 "", "| Group | Courses | Complete | Partial | Quizzes | Raw questions | Distinct fingerprints | Exact duplicate clusters |",
                 "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for item in summaries:
            lines.append(f"| {item['certification_code']} | {item['courses_in_inventory']} | "
                         f"{item['courses_complete']} | {item['courses_partial']} | {item['exams_discovered']} | "
                         f"{item['raw_question_instances']} | {item['distinct_question_fingerprints']} | "
                         f"{item['exact_duplicate_clusters']} |")
        lines.extend(["", f"Cross-certification duplicate clusters: {len(cross_group)}. These were flagged, not merged.",
                      "", "Partial courses retain their source questions and warnings in `progress.json`. "
                      "All question text, answer text, and PDFs remain under this gitignored local directory.",
                      "", "See `progress.md` for every course and each group folder for JSON, HTML, Markdown, PDF, "
                      "summary and duplicate evidence.", ""])
        (root / "summary.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
