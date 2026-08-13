from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape, unescape
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass


class PracticeExportError(RuntimeError):
    pass


@dataclass
class PracticeExportResult:
    course_id: str | None
    item_count: int
    assessment_count: int
    output_json: Path
    output_markdown: Path
    output_html: Path
    output_pdf: Path
    output_set_pdfs: list[Path]
    warnings: list[str]


def export_practice_tests(course_url: str, cookies_path: Path, output_dir: Path) -> PracticeExportResult:
    """Best-effort export of quiz/practice-test data visible to the authenticated user.

    Udemy does not provide a stable public learner export API for practice tests. This
    function only calls normal authenticated JSON endpoints with user-supplied cookies
    and records clear warnings when those endpoints are unavailable.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    session = _build_session(cookies_path, course_url)
    course_id, title, warnings = _discover_course(session, course_url)

    practice_items: list[dict[str, Any]] = []
    if course_id:
        items, curriculum_warnings = _fetch_curriculum(session, course_url, course_id)
        warnings.extend(curriculum_warnings)
        practice_items = [item for item in items if _looks_like_practice_test(item)]
    else:
        warnings.append("Could not discover the Udemy course id from the course page.")

    exported_tests: list[dict[str, Any]] = []
    assessment_total = 0
    course_prefix = _friendly_course_prefix(title, course_url)
    for item in practice_items:
        item_id = _item_id(item)
        item_title = _item_title(item)
        set_index = len(exported_tests) + 1
        display_title = _friendly_test_title(course_prefix, item_title, set_index)
        item_version = _item_version(item)
        expected_count = _item_expected_count(item)
        assessments: list[dict[str, Any]] = []
        item_warnings: list[str] = []
        if item_id:
            assessments, item_warnings = _fetch_assessments(session, course_url, str(item_id), item_version)
        else:
            item_warnings.append(f"Could not determine a quiz id for '{display_title}'.")

        if expected_count is not None and len(assessments) != expected_count:
            item_warnings.append(
                f"{display_title} expected {expected_count} questions from curriculum metadata "
                f"but exported {len(assessments)}."
            )

        warnings.extend(item_warnings)
        assessment_total += len(assessments)
        exported_tests.append(
            {
                "id": item_id,
                "title": display_title,
                "original_title": item_title,
                "set_index": set_index,
                "assessment_version": item_version,
                "expected_assessment_count": expected_count,
                "curriculum_item": item,
                "assessments": assessments,
            }
        )

    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "course_url": course_url,
        "course_id": course_id,
        "course_title": title,
        "practice_set_prefix": course_prefix,
        "practice_tests": exported_tests,
        "warnings": warnings,
    }

    file_stem = f"{_slugify_file_stem(course_prefix)}-practice-tests"
    json_path = output_dir / f"{file_stem}.json"
    markdown_path = output_dir / f"{file_stem}.md"
    html_path = output_dir / f"{file_stem}.html"
    pdf_path = output_dir / f"{file_stem}.pdf"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text(_to_markdown(payload), encoding="utf-8")
    html_path.write_text(_to_html(payload), encoding="utf-8")
    _to_pdf(payload, pdf_path)
    set_pdf_paths = _write_set_pdfs(payload, output_dir)

    return PracticeExportResult(
        course_id=course_id,
        item_count=len(exported_tests),
        assessment_count=assessment_total,
        output_json=json_path,
        output_markdown=markdown_path,
        output_html=html_path,
        output_pdf=pdf_path,
        output_set_pdfs=set_pdf_paths,
        warnings=warnings,
    )


def _build_session(cookies_path: Path, referer: str) -> requests.Session:
    jar = MozillaCookieJar()
    try:
        jar.load(str(cookies_path), ignore_discard=True, ignore_expires=True)
    except Exception as exc:  # pragma: no cover - exact parser errors vary by Python.
        raise PracticeExportError("Cookies file must be in Netscape cookies.txt format.") from exc

    session = requests.Session()
    session.cookies = jar
    session.headers.update(
        {
            "Accept": "application/json, text/plain, */*",
            "Referer": referer,
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
            ),
        }
    )
    return session


def _discover_course(session: requests.Session, course_url: str) -> tuple[str | None, str | None, list[str]]:
    warnings: list[str] = []
    response = session.get(course_url, timeout=30)
    if response.status_code >= 400:
        warnings.append(f"Course page returned HTTP {response.status_code}.")
        return None, None, warnings

    text = response.text
    course_id = _first_match(
        text,
        [
            r"courseId=(\d+)",
            r"/course/\d+x\d+/(\d+)_",
            r'"courseId"\s*:\s*(\d+)',
            r'"course_id"\s*:\s*(\d+)',
            r"data-clp-course-id=[\"'](\d+)[\"']",
            r"/courses/(\d+)/subscriber-curriculum-items",
        ],
    )
    title = _first_match(
        text,
        [
            r"<meta[^>]+property=[\"']og:title[\"'][^>]+content=[\"']([^\"']{2,180})[\"']",
            r"<meta[^>]+content=[\"']([^\"']{2,180})[\"'][^>]+property=[\"']og:title[\"']",
            r"<title>([^<]{2,180})</title>",
            r'"course_title"\s*:\s*"([^"]{2,180})"',
            r'"title"\s*:\s*"([^"]{2,180})"',
        ],
    )
    return course_id, _clean_text(title) if title else None, warnings


def _fetch_curriculum(
    session: requests.Session, course_url: str, course_id: str
) -> tuple[list[dict[str, Any]], list[str]]:
    host = _base_url(course_url)
    cached_params = {
        "page_size": "200",
        "fields[asset]": "title,asset_type",
        "fields[chapter]": "title,object_index",
        "fields[lecture]": "title,object_index,asset",
        "fields[practice]": "id,title,object_index,num_assessments,version,duration,pass_percent,description,is_draft,changelog",
        "fields[quiz]": "id,title,object_index,type,num_assessments,version,duration,pass_percent,description,is_draft,changelog",
    }
    legacy_params = {
        "page_size": "200",
        "fields[asset]": "@all",
        "fields[chapter]": "@all",
        "fields[lecture]": "@all",
        "fields[practice]": "@all",
        "fields[quiz]": "@all",
    }
    endpoints: list[tuple[str, dict[str, str] | None]] = [
        (f"{host}/api-2.0/courses/{course_id}/cached-subscriber-curriculum-items", cached_params),
        (f"{host}/api-2.0/courses/{course_id}/subscriber-curriculum-items/", legacy_params),
    ]
    warnings: list[str] = []
    for endpoint, params in endpoints:
        items, endpoint_warnings = _fetch_paginated(session, endpoint, params=params, label="curriculum")
        if items:
            return items, warnings + endpoint_warnings
        warnings.extend(endpoint_warnings)
    return [], warnings


def _fetch_assessments(
    session: requests.Session, course_url: str, quiz_id: str, version: int | None = None
) -> tuple[list[dict[str, Any]], list[str]]:
    host = _base_url(course_url)
    params = {
        "page_size": "250",
        "fields[assessment]": "@all",
        "fields[answer]": "@all",
    }
    if version is not None:
        params["version"] = str(version)
    endpoints = [
        f"{host}/api-2.0/quizzes/{quiz_id}/assessments/",
        f"{host}/api-2.0/practice-tests/{quiz_id}/assessments/",
    ]

    warnings: list[str] = []
    for endpoint in endpoints:
        items, endpoint_warnings = _fetch_paginated(
            session, endpoint, params=params, label=f"assessments for quiz {quiz_id}"
        )
        if items:
            return items, warnings + endpoint_warnings
        warnings.extend(endpoint_warnings)

    return [], warnings


def _fetch_paginated(
    session: requests.Session, url: str, params: dict[str, str] | None, label: str
) -> tuple[list[dict[str, Any]], list[str]]:
    items: list[dict[str, Any]] = []
    warnings: list[str] = []
    next_url: str | None = url
    next_params = params
    pages = 0

    while next_url and pages < 100:
        pages += 1
        try:
            response = session.get(next_url, params=next_params, timeout=30)
        except requests.RequestException as exc:
            warnings.append(f"Could not fetch {label}: {exc}.")
            break

        next_params = None
        if response.status_code in {401, 403}:
            warnings.append(f"{label} endpoint rejected the authenticated request with HTTP {response.status_code}.")
            break
        if response.status_code == 404:
            warnings.append(f"{label} endpoint was not available.")
            break
        if response.status_code >= 400:
            warnings.append(f"{label} endpoint returned HTTP {response.status_code}.")
            break

        try:
            data = response.json()
        except ValueError:
            warnings.append(f"{label} endpoint did not return JSON.")
            break

        if isinstance(data, dict):
            results = data.get("results", [])
            if isinstance(results, list):
                items.extend(item for item in results if isinstance(item, dict))
            raw_next = data.get("next")
            next_url = urljoin(next_url, raw_next) if raw_next else None
        elif isinstance(data, list):
            items.extend(item for item in data if isinstance(item, dict))
            next_url = None
        else:
            warnings.append(f"{label} endpoint returned an unexpected JSON shape.")
            break

    if pages >= 100:
        warnings.append(f"Stopped paginating {label} after 100 pages.")

    return items, warnings


def _looks_like_practice_test(item: dict[str, Any]) -> bool:
    haystack = " ".join(
        _clean_text(str(value)).lower()
        for value in [
            item.get("_class"),
            item.get("type"),
            item.get("object_type"),
            item.get("asset_type"),
            item.get("title"),
            item.get("display_title"),
        ]
        if value
    )
    return "practice" in haystack or "quiz" in haystack or "assessment" in haystack


def _item_id(item: dict[str, Any]) -> Any:
    for key in ("id", "quiz_id", "object_id"):
        if item.get(key):
            return item[key]
    for key in ("quiz", "practice", "asset"):
        nested = item.get(key)
        if isinstance(nested, dict) and nested.get("id"):
            return nested["id"]
    return None


def _item_title(item: dict[str, Any]) -> str:
    for key in ("title", "display_title", "object_title"):
        if item.get(key):
            return _clean_text(str(item[key]))
    return f"Practice test {str(_item_id(item) or 'unknown')}"


def _item_version(item: dict[str, Any]) -> int | None:
    return _int_or_none(_nested_item_value(item, ("version",)))


def _item_expected_count(item: dict[str, Any]) -> int | None:
    return _int_or_none(
        _nested_item_value(item, ("num_assessments", "assessment_count", "num_questions", "question_count"))
    )


def _test_meta_text(test: dict[str, Any]) -> str:
    parts = [_test_question_count_text(test)]
    version = _int_or_none(test.get("assessment_version"))
    if version is not None:
        parts.append(f"Version: {version}")
    return " | ".join(part for part in parts if part)


def _test_heading(test: dict[str, Any]) -> str:
    title = _clean_text(str(test.get("title") or "Practice test"))
    details = _test_meta_text(test).replace(" | ", ", ")
    return f"{title} ({details})" if details else title


def _test_question_count_text(test: dict[str, Any]) -> str:
    actual = len(test.get("assessments") or [])
    expected = _int_or_none(test.get("expected_assessment_count"))
    if expected is None or expected == actual:
        return f"Questions: {actual}"
    return f"Questions: {actual} of {expected}"


def _nested_item_value(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if item.get(key) not in (None, ""):
            return item[key]
    for nested_key in ("quiz", "practice", "asset"):
        nested = item.get(nested_key)
        if isinstance(nested, dict):
            for key in keys:
                if nested.get(key) not in (None, ""):
                    return nested[key]
    return None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _friendly_course_prefix(course_title: str | None, course_url: str) -> str:
    raw = course_title or _title_from_slug(_udemy_course_slug(course_url)) or "Practice Tests"
    text = _clean_text(str(raw).replace("-", " ").replace("_", " "))
    text = re.sub(r"\s*\|\s*Udemy.*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*\d+\s+", "", text)
    text = re.sub(r"\bCOF\s*-?\s*C0?2\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bpractice\s+(exams?|tests?)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bmock\s+(exams?|tests?)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(exam|test)\s+questions?\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bquestion\s+bank\b", " ", text, flags=re.IGNORECASE)
    text = _clean_text(text)
    return text or "Practice Tests"


def _friendly_test_title(course_prefix: str, original_title: str, set_index: int) -> str:
    original = _clean_text(original_title)
    number = _first_int(original) or set_index
    generic = re.sub(r"\d+", "", original).strip().lower()
    generic = re.sub(r"\s+", " ", generic)
    if generic in {"practice", "practice exam", "practice test", "exam", "test"}:
        return f"{course_prefix} Set {number}"
    if original.lower().startswith(course_prefix.lower()):
        return original
    return f"{course_prefix} Set {number}" if number else original


def _first_int(value: str) -> int | None:
    match = re.search(r"\d+", value)
    return int(match.group(0)) if match else None


def _slugify_file_stem(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9]+", "-", _clean_text(value).lower())
    safe = "-".join(part for part in safe.split("-") if part)
    return safe[:90] or "practice-tests"


def _udemy_course_slug(course_url: str) -> str | None:
    parsed = urlparse(course_url)
    parts = [part for part in parsed.path.split("/") if part]
    if "course" not in parts:
        return None
    index = parts.index("course")
    return parts[index + 1] if len(parts) > index + 1 else None


def _title_from_slug(value: str | None) -> str | None:
    if not value:
        return None
    return " ".join(part.capitalize() for part in re.split(r"[-_\s]+", value) if part)


def _write_set_pdfs(payload: dict[str, Any], output_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for test in payload.get("practice_tests") or []:
        title = _clean_text(str(test.get("title") or "Practice set"))
        set_payload = {
            **payload,
            "practice_tests": [test],
            "warnings": [],
        }
        path = output_dir / f"{_slugify_file_stem(title)}.pdf"
        _to_pdf(set_payload, path)
        paths.append(path)
    return paths


def _to_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Practice Tests",
        "",
        f"Course: {_clean_text(str(payload.get('course_title') or payload.get('course_url') or 'Unknown'))}",
        f"Course ID: {payload.get('course_id') or 'Unknown'}",
        f"Exported: {payload.get('exported_at')}",
        "",
    ]

    warnings = payload.get("warnings") or []
    if warnings:
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {_clean_text(str(warning))}" for warning in warnings)
        lines.append("")

    tests = payload.get("practice_tests") or []
    if not tests:
        lines.extend(["No practice tests or quizzes were exported.", ""])
        return "\n".join(lines)

    for test in tests:
        lines.extend([f"## {_clean_text(str(test.get('title') or 'Practice test'))}", ""])
        meta_text = _test_meta_text(test)
        if meta_text:
            lines.extend([meta_text, ""])
        assessments = test.get("assessments") or []
        if not assessments:
            lines.extend(["No questions were available from the authenticated endpoint.", ""])
            continue

        for index, assessment in enumerate(assessments, start=1):
            prompt = _assessment_prompt(assessment)
            lines.extend([f"### {index}. {prompt or 'Question'}", ""])
            answers = _assessment_answers(assessment)
            if answers:
                lines.extend(f"- {_answer_label(answer_index)}. {_clean_text(answer)}" for answer_index, answer in enumerate(answers))
                lines.append("")
            correct = assessment.get("correct_response") or assessment.get("correct_responses")
            if correct:
                lines.extend([f"Correct response: `{_correct_response_text(correct)}`", ""])
            explanation = _assessment_explanation(assessment)
            if explanation:
                lines.extend([f"Explanation: {_clean_text(explanation)}", ""])

    return "\n".join(lines)


def _to_html(payload: dict[str, Any]) -> str:
    title = _clean_text(str(payload.get("course_title") or "Practice Tests"))
    warnings = payload.get("warnings") or []
    tests = payload.get("practice_tests") or []
    warning_html = ""
    if warnings:
        warning_html = "<section><h2>Warnings</h2><ul>{}</ul></section>".format(
            "".join(f"<li>{escape(_clean_text(str(warning)))}</li>" for warning in warnings)
        )

    test_sections = []
    for test in tests:
        assessments = test.get("assessments") or []
        questions = []
        for index, assessment in enumerate(assessments, start=1):
            prompt = escape(_assessment_prompt(assessment) or "Question")
            answers = _assessment_answers(assessment)
            answer_html = ""
            if answers:
                answer_html = "<ul class=\"answers\">{}</ul>".format(
                    "".join(
                        f"<li><strong>{_answer_label(answer_index)}.</strong> {escape(_clean_text(answer))}</li>"
                        for answer_index, answer in enumerate(answers)
                    )
                )
            correct = assessment.get("correct_response") or assessment.get("correct_responses")
            correct_html = f"<p><strong>Correct:</strong> {escape(_correct_response_text(correct))}</p>" if correct else ""
            explanation = _assessment_explanation(assessment)
            explanation_html = (
                f"<p><strong>Explanation:</strong> {escape(_clean_text(explanation))}</p>" if explanation else ""
            )
            questions.append(
                f"<article class=\"question\"><h3>{index}. {prompt}</h3>{answer_html}{correct_html}{explanation_html}</article>"
            )

        body = "".join(questions) if questions else "<p>No questions were available from the authenticated endpoint.</p>"
        meta_text = _test_meta_text(test)
        meta_html = f"<p class=\"meta\">{escape(meta_text)}</p>" if meta_text else ""
        test_sections.append(
            "<section class=\"test\"><h2>{}</h2>{}{}</section>".format(
                escape(_clean_text(str(test.get("title") or "Practice test"))), meta_html, body
            )
        )

    if not test_sections:
        test_sections.append("<section><p>No practice tests or quizzes were exported.</p></section>")

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{escape(title)}</title>
    <style>
      body {{
        margin: 0;
        background: #f6f4ef;
        color: #222324;
        font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        line-height: 1.55;
      }}
      main {{
        max-width: 980px;
        margin: 0 auto;
        padding: 32px 18px 64px;
      }}
      header, section {{
        background: #fff;
        border: 1px solid #d9d3c7;
        border-radius: 8px;
        padding: 20px;
        margin-bottom: 14px;
      }}
      h1, h2, h3, p {{
        margin-top: 0;
      }}
      h1 {{
        font-size: 1.7rem;
      }}
      h2 {{
        font-size: 1.2rem;
      }}
      .meta {{
        color: #67645c;
      }}
      .question {{
        border-top: 1px solid #d9d3c7;
        padding-top: 16px;
        margin-top: 16px;
      }}
      ul.answers {{
        list-style: none;
        padding-left: 0;
      }}
      ul.answers li {{
        margin-bottom: 6px;
      }}
      code {{
        background: #f0ede6;
        padding: 2px 5px;
        border-radius: 5px;
      }}
    </style>
  </head>
  <body>
    <main>
      <header>
        <h1>{escape(title)}</h1>
        <p class="meta">Course ID: {escape(str(payload.get("course_id") or "Unknown"))}</p>
        <p class="meta">Exported: {escape(str(payload.get("exported_at") or ""))}</p>
      </header>
      {warning_html}
      {"".join(test_sections)}
    </main>
  </body>
</html>
"""


def _to_pdf(payload: dict[str, Any], output_path: Path) -> None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
    except ImportError as exc:  # pragma: no cover - covered by deployment dependency checks.
        raise PracticeExportError("PDF export requires the reportlab package.") from exc

    styles = getSampleStyleSheet()
    normal = ParagraphStyle(
        "PracticeNormal",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        spaceAfter=6,
    )
    title_style = ParagraphStyle(
        "PracticeTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        spaceAfter=12,
    )
    meta_style = ParagraphStyle(
        "PracticeMeta",
        parent=normal,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#5f6368"),
        fontSize=8.5,
        leading=11,
        spaceAfter=4,
    )
    section_style = ParagraphStyle(
        "PracticeSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        spaceBefore=12,
        spaceAfter=8,
        textColor=colors.HexColor("#0d5f59"),
    )
    question_style = ParagraphStyle(
        "PracticeQuestion",
        parent=normal,
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13.5,
        spaceBefore=8,
        spaceAfter=7,
    )
    answer_style = ParagraphStyle(
        "PracticeAnswer",
        parent=normal,
        leftIndent=14,
        firstLineIndent=-14,
        spaceAfter=4,
    )
    correct_style = ParagraphStyle(
        "PracticeCorrect",
        parent=normal,
        textColor=colors.HexColor("#075b55"),
        fontName="Helvetica-Bold",
        spaceBefore=4,
    )
    explanation_style = ParagraphStyle(
        "PracticeExplanation",
        parent=normal,
        textColor=colors.HexColor("#424242"),
        leftIndent=8,
        borderColor=colors.HexColor("#d9d3c7"),
        borderWidth=0.5,
        borderPadding=6,
        backColor=colors.HexColor("#f7f4ee"),
        spaceBefore=4,
        spaceAfter=8,
    )
    warning_style = ParagraphStyle(
        "PracticeWarning",
        parent=normal,
        textColor=colors.HexColor("#8a4b00"),
    )

    story: list[Any] = []
    course_title = _clean_text(str(payload.get("course_title") or "Practice Tests"))
    story.append(Paragraph(_pdf_escape(course_title), title_style))
    story.append(Paragraph(f"Course ID: {_pdf_escape(str(payload.get('course_id') or 'Unknown'))}", meta_style))
    story.append(Paragraph(f"Source: {_pdf_escape(str(payload.get('course_url') or ''))}", meta_style))
    story.append(Paragraph(f"Exported: {_pdf_escape(str(payload.get('exported_at') or ''))}", meta_style))
    story.append(Spacer(1, 0.16 * inch))

    warnings = payload.get("warnings") or []
    if warnings:
        story.append(Paragraph("Warnings", section_style))
        for warning in warnings:
            story.append(Paragraph(f"- {_pdf_escape(_clean_text(str(warning)))}", warning_style))

    tests = payload.get("practice_tests") or []
    if not tests:
        story.append(Paragraph("No practice tests or quizzes were exported.", normal))
    for test_index, test in enumerate(tests):
        if test_index:
            story.append(PageBreak())
        assessments = test.get("assessments") or []
        heading = _test_heading(test)
        story.append(Paragraph(_pdf_escape(heading), section_style))
        if not assessments:
            story.append(Paragraph("No questions were available from the authenticated endpoint.", normal))
            continue

        for index, assessment in enumerate(assessments, start=1):
            prompt = _assessment_prompt(assessment) or "Question"
            story.append(Paragraph(f"{index}. {_pdf_escape(prompt)}", question_style))
            for answer_index, answer in enumerate(_assessment_answers(assessment)):
                answer_text = f"{_answer_label(answer_index)}. {_clean_text(answer)}"
                story.append(Paragraph(_pdf_escape(answer_text), answer_style))
            correct = assessment.get("correct_response") or assessment.get("correct_responses")
            if correct:
                story.append(Paragraph(f"Correct: {_pdf_escape(_correct_response_text(correct))}", correct_style))
            explanation = _assessment_explanation(assessment)
            if explanation:
                story.append(Paragraph(f"<b>Explanation:</b> {_pdf_escape(_clean_text(explanation))}", explanation_style))

    def add_page_number(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#67645c"))
        canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 0.38 * inch, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        title=course_title,
        author="Local Media Downloader",
    )
    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)


def _assessment_prompt(assessment: dict[str, Any]) -> str:
    prompt = _assessment_prompt_data(assessment)
    if prompt:
        for key in ("question", "prompt", "title", "body", "text", "plain_text", "html"):
            text = _plain(prompt.get(key))
            if text:
                return _clean_text(text)

    for key in ("prompt", "question", "title", "body"):
        text = _plain(assessment.get(key))
        if text:
            return _clean_text(text)
    return ""


def _assessment_answers(assessment: dict[str, Any]) -> list[str]:
    prompt = _assessment_prompt_data(assessment)
    raw = (
        prompt.get("answers")
        or prompt.get("response_options")
        or prompt.get("answer")
        or assessment.get("answers")
        or assessment.get("response_options")
        or assessment.get("answer")
    )
    if isinstance(raw, list):
        answers = []
        for item in raw:
            if isinstance(item, dict):
                text = _plain(item.get("text") or item.get("body") or item.get("answer") or item)
                if item.get("is_correct") is True:
                    text = f"{text} [correct]"
                if text:
                    answers.append(text)
            else:
                text = _plain(item)
                if text:
                    answers.append(text)
        return answers
    text = _plain(raw)
    return [text] if text else []


def _assessment_explanation(assessment: dict[str, Any]) -> str:
    prompt = _assessment_prompt_data(assessment)
    for source in (prompt, assessment):
        for key in ("explanation", "feedback", "rationale", "solution"):
            text = _plain(source.get(key))
            if text:
                return _clean_text(text)
    return ""


def _assessment_prompt_data(assessment: dict[str, Any]) -> dict[str, Any]:
    prompt = assessment.get("prompt")
    return prompt if isinstance(prompt, dict) else {}


def _correct_response_text(value: Any) -> str:
    if isinstance(value, list):
        values = value
    elif isinstance(value, tuple):
        values = list(value)
    else:
        values = [value]

    labels: list[str] = []
    for item in values:
        text = _clean_text(_plain(item))
        if len(text) == 1 and text.isalpha():
            labels.append(text.upper())
        else:
            labels.append(text)
    return ", ".join(label for label in labels if label)


def _answer_label(index: int) -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if index < len(alphabet):
        return alphabet[index]
    return str(index + 1)


def _plain(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        for key in ("plain_text", "text", "html", "body", "title", "value"):
            if key in value:
                text = _plain(value[key])
                if text:
                    return text
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, list):
        return " ".join(_plain(item) for item in value if _plain(item))
    return str(value)


def _clean_text(value: str) -> str:
    text = unescape(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\\n", " ").replace("\\u002F", "/")
    return re.sub(r"\s+", " ", text).strip()


def _pdf_escape(value: str) -> str:
    return escape(_clean_text(value), quote=False).replace("\n", "<br/>")


def _first_match(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def _base_url(course_url: str) -> str:
    parsed = urlparse(course_url)
    return f"{parsed.scheme}://{parsed.netloc}"
