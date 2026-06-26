from __future__ import annotations

import json
import re
from html import escape
from dataclasses import dataclass
from datetime import datetime, timezone
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
    for item in practice_items:
        item_id = _item_id(item)
        item_title = _item_title(item)
        assessments: list[dict[str, Any]] = []
        item_warnings: list[str] = []
        if item_id:
            assessments, item_warnings = _fetch_assessments(session, course_url, str(item_id))
        else:
            item_warnings.append(f"Could not determine a quiz id for '{item_title}'.")

        warnings.extend(item_warnings)
        assessment_total += len(assessments)
        exported_tests.append(
            {
                "id": item_id,
                "title": item_title,
                "curriculum_item": item,
                "assessments": assessments,
            }
        )

    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "course_url": course_url,
        "course_id": course_id,
        "course_title": title,
        "practice_tests": exported_tests,
        "warnings": warnings,
    }

    json_path = output_dir / "practice-tests.json"
    markdown_path = output_dir / "practice-tests.md"
    html_path = output_dir / "practice-tests.html"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text(_to_markdown(payload), encoding="utf-8")
    html_path.write_text(_to_html(payload), encoding="utf-8")

    return PracticeExportResult(
        course_id=course_id,
        item_count=len(exported_tests),
        assessment_count=assessment_total,
        output_json=json_path,
        output_markdown=markdown_path,
        output_html=html_path,
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
    title = _first_match(text, [r'"title"\s*:\s*"([^"]{2,180})"', r"<title>([^<]{2,180})</title>"])
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
        "fields[practice]": "title,object_index",
        "fields[quiz]": "title,object_index,type",
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
    session: requests.Session, course_url: str, quiz_id: str
) -> tuple[list[dict[str, Any]], list[str]]:
    host = _base_url(course_url)
    params = {
        "page_size": "250",
        "version": "1",
        "fields[assessment]": "@all",
        "fields[answer]": "@all",
    }
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
        assessments = test.get("assessments") or []
        if not assessments:
            lines.extend(["No questions were available from the authenticated endpoint.", ""])
            continue

        for index, assessment in enumerate(assessments, start=1):
            prompt = _assessment_prompt(assessment)
            lines.extend([f"### {index}. {prompt or 'Question'}", ""])
            answers = _assessment_answers(assessment)
            if answers:
                lines.extend(f"- {_clean_text(answer)}" for answer in answers)
                lines.append("")
            correct = assessment.get("correct_response") or assessment.get("correct_responses")
            if correct:
                lines.extend([f"Correct response: `{_clean_text(str(correct))}`", ""])
            explanation = _plain(assessment.get("explanation") or assessment.get("feedback"))
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
                answer_html = "<ol>{}</ol>".format(
                    "".join(f"<li>{escape(_clean_text(answer))}</li>" for answer in answers)
                )
            correct = assessment.get("correct_response") or assessment.get("correct_responses")
            correct_html = f"<p><strong>Correct:</strong> {escape(_clean_text(str(correct)))}</p>" if correct else ""
            explanation = _plain(assessment.get("explanation") or assessment.get("feedback"))
            explanation_html = (
                f"<p><strong>Explanation:</strong> {escape(_clean_text(explanation))}</p>" if explanation else ""
            )
            questions.append(
                f"<article class=\"question\"><h3>{index}. {prompt}</h3>{answer_html}{correct_html}{explanation_html}</article>"
            )

        body = "".join(questions) if questions else "<p>No questions were available from the authenticated endpoint.</p>"
        test_sections.append(
            "<section class=\"test\"><h2>{}</h2>{}</section>".format(
                escape(_clean_text(str(test.get("title") or "Practice test"))), body
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
      ol {{
        padding-left: 24px;
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


def _assessment_prompt(assessment: dict[str, Any]) -> str:
    for key in ("prompt", "question", "title", "body"):
        text = _plain(assessment.get(key))
        if text:
            return _clean_text(text)
    return ""


def _assessment_answers(assessment: dict[str, Any]) -> list[str]:
    raw = assessment.get("answers") or assessment.get("response_options") or assessment.get("answer")
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
    text = re.sub(r"<[^>]+>", " ", value)
    text = text.replace("\\n", " ").replace("\\u002F", "/")
    return re.sub(r"\s+", " ", text).strip()


def _first_match(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def _base_url(course_url: str) -> str:
    parsed = urlparse(course_url)
    return f"{parsed.scheme}://{parsed.netloc}"
