"""AI-assisted instructional synthesis grounded in this lesson's real evidence.

Deliberately no 'summary' fallback: if an actual model is unavailable or produces
generic/inadequate output, reject it instead of passing an extractive transcript
outline off as a teaching course. No unsupported outside knowledge is added.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class LearningGuideError(RuntimeError):
    """An instructional artifact was not generated or did not pass quality gates."""


def learning_model() -> str:
    return os.environ.get("CI_LEARNING_MODEL", "").strip()


def _endpoint() -> str:
    value = os.environ.get("CI_OLLAMA_URL", "http://host.docker.internal:11434").rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme != "http" or parsed.hostname not in {"host.docker.internal", "127.0.0.1", "localhost"} or parsed.username or parsed.password or parsed.path not in {"", "/"}:
        raise LearningGuideError("CI_OLLAMA_URL must point to a local Ollama server (host.docker.internal or localhost).")
    return value


def load_visual_evidence(download_root: Path | None, lesson: dict[str, Any]) -> dict[str, Any] | None:
    """Read only a same-media lesson package. No arbitrary user paths or network."""
    if download_root is None or not lesson.get("media_path"):
        return None
    root = Path(download_root).resolve()
    media = (root / lesson["media_path"]).resolve()
    if not media.is_relative_to(root) or not media.is_file():
        return None
    candidates = [media.parent / f".visual-{lesson['id']}"]
    for folder in sorted(media.parent.iterdir()):
        if folder.is_dir() and folder.name.startswith(f".{media.stem}.") and folder.name.endswith(".learning"):
            candidates.append(folder / "visuals")
    for candidate in candidates:
        item = (candidate / "visual-manifest.json").resolve()
        if not item.is_relative_to(root) or not item.is_file() or item.stat().st_size > 2_000_000:
            continue
        try:
            data = json.loads(item.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                return data
        except (ValueError, OSError):
            continue
    return None


def _transcript_evidence(transcript: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    all_segments = {}
    for position, item in enumerate(transcript.get("segments") or []):
        text = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
        if not text:
            continue
        key = item.get("segment_index", position)
        if not isinstance(key, int) or isinstance(key, bool) or key in all_segments:
            continue
        all_segments[key] = {
            "transcript_id": transcript.get("id"),
            "segment_index": key, "start_ms": item.get("start_ms"),
            "end_ms": item.get("end_ms"), "text": text,
        }
    if len(all_segments) < 8:
        raise LearningGuideError("A substantial transcript is needed for a full lesson; fewer than 8 segments were found.")
    # Preserve all segments for the POC-sized lecture. Longer courses are sampled,
    # and citations may only refer to supplied evidence IDs.
    ordered = sorted(all_segments.values(), key=lambda x: x["segment_index"])
    if len(ordered) > 320:
        indices = sorted({round(i * (len(ordered) - 1) / 319) for i in range(320)})
        ordered = [ordered[i] for i in indices]
    return ordered, {item["segment_index"]: item for item in ordered}


def _visual_evidence(manifest: dict[str, Any] | None) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if not manifest:
        return [], {}
    all_items = []
    for item in manifest.get("items") or []:
        if not isinstance(item, dict):
            continue
        frame = str(item.get("frame_file") or "")
        if not re.fullmatch(r"frames/(?:periodic|scene)-\d{4}\.jpg", frame):
            continue
        ocr = item.get("ocr") or {}
        all_items.append({
            "frame_file": frame, "timestamp_ms": item.get("timestamp_ms"),
            "category": str(item.get("category") or "unclassified_visual"),
            "ocr": str(ocr.get("text") or "")[:550],
        })
    all_items.sort(key=lambda x: (x["timestamp_ms"] is None, x["timestamp_ms"] or 0))
    if len(all_items) > 26:
        priority = [i for i, frame in enumerate(all_items) if frame["category"] in {"code_candidate", "diagram_candidate"}]
        spread = [round(i * (len(all_items) - 1) / 25) for i in range(26)]
        selection = sorted(set(priority[:10] + spread))
        if len(selection) > 30:
            selection = selection[:30]
        all_items = [all_items[i] for i in selection]
    return all_items, {item["frame_file"]: item for item in all_items}


def _text(value: Any, *, minimum: int, maximum: int, field: str) -> str:
    if not isinstance(value, str):
        raise LearningGuideError(f"{field} must be written prose, not an empty or structured placeholder.")
    value = re.sub(r"\s+", " ", value).strip()
    if not minimum <= len(value) <= maximum:
        raise LearningGuideError(f"{field} needs {minimum}–{maximum} characters of meaningful instruction.")
    if re.search(r"\b(?:transcript section|topic \d+|as an ai language model)\b", value, re.I):
        raise LearningGuideError(f"{field} contains placeholder or non-instructional writing.")
    return value


def _citations(raw: Any, source: dict[int, dict[str, Any]], label: str) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= 6:
        raise LearningGuideError(f"{label} must cite 1–6 specific source segments.")
    found = []
    for value in raw:
        if not isinstance(value, int) or isinstance(value, bool) or value not in source:
            raise LearningGuideError(f"{label} references an unknown transcript segment.")
        if value not in [c["segment_index"] for c in found]:
            found.append(dict(source[value]))
    return found


def _visuals(raw: Any, available: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if raw is None:
        raw = []
    if not isinstance(raw, list) or len(raw) > 6:
        raise LearningGuideError("Visual references must be a list of at most six frame filenames.")
    frames = []
    for name in raw:
        if not isinstance(name, str) or name not in available:
            raise LearningGuideError("The guide cites a frame not present in the analyzed lecture.")
        if name not in [v["frame_file"] for v in frames]:
            frames.append(dict(available[name]))
    return frames


def validate_guide(raw: dict[str, Any], transcript: dict[str, Any],
                   source: dict[int, dict[str, Any]],
                   visual: dict[str, dict[str, Any]], model: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise LearningGuideError("Local model did not return a JSON learning guide.")
    overview = _text(raw.get("overview"), minimum=180, maximum=2000, field="overview")
    takeaways = raw.get("takeaways")
    chapters = raw.get("chapters")
    outcomes = raw.get("learning_outcomes")
    examples = raw.get("worked_example")
    practice = raw.get("practice")
    if not isinstance(takeaways, list) or not 4 <= len(takeaways) <= 10:
        raise LearningGuideError("Guide needs 4–10 meaningful, source-cited takeaways.")
    if not isinstance(chapters, list) or not 3 <= len(chapters) <= 8:
        raise LearningGuideError("Guide needs 3–8 instructional chapters, not a short recap.")
    if not isinstance(outcomes, list) or not 3 <= len(outcomes) <= 8:
        raise LearningGuideError("Guide needs 3–8 specific learner outcomes.")
    if not isinstance(examples, dict) or not isinstance(practice, list) or not 2 <= len(practice) <= 8:
        raise LearningGuideError("A worked example and at least two answered exercises are required.")

    result = {
        "title": _text(raw.get("title"), minimum=10, maximum=140, field="title"),
        "overview": overview,
        "status": "ai_draft_requires_review",
        "generator": "local-ollama-evidence-validated",
        "model": model,
        "evidence_limits": [
            "Source references identify relevant transcript and sampled frames; they do not prove every generated claim is correct.",
            "Audio word error rate and all unobserved visual content remain unverified.",
            "Examples and recommendations must be independently validated before operational use.",
        ],
        "learning_outcomes": [_text(x, minimum=35, maximum=400, field="learning outcome") for x in outcomes],
        "takeaways": [], "chapters": [], "practice": [],
    }
    for i, item in enumerate(takeaways, 1):
        if not isinstance(item, dict):
            raise LearningGuideError("Takeaways must be grounded instructional items.")
        result["takeaways"].append({
            "text": _text(item.get("text"), minimum=75, maximum=750, field=f"takeaway {i}"),
            "citations": _citations(item.get("segment_ids"), source, f"takeaway {i}"),
        })
    chapter_titles = set()
    all_source_indices = set()
    for i, item in enumerate(chapters, 1):
        if not isinstance(item, dict):
            raise LearningGuideError("Each chapter must have an actual explanation.")
        heading = _text(item.get("heading"), minimum=8, maximum=130, field=f"chapter {i} heading")
        if heading.casefold() in chapter_titles:
            raise LearningGuideError("Repeated chapter titles indicate generic or duplicated material.")
        chapter_titles.add(heading.casefold())
        steps = item.get("steps")
        if not isinstance(steps, list) or not 2 <= len(steps) <= 9:
            raise LearningGuideError(f"Chapter {i} needs at least two concrete, step-by-step instructions.")
        citations = _citations(item.get("segment_ids"), source, f"chapter {i}")
        all_source_indices.update(c["segment_index"] for c in citations)
        result["chapters"].append({
            "heading": heading,
            "explanation": _text(item.get("explanation"), minimum=180, maximum=2500, field=f"chapter {i} explanation"),
            "why_it_matters": _text(item.get("why_it_matters"), minimum=80, maximum=1100, field=f"chapter {i} importance"),
            "steps": [_text(step, minimum=40, maximum=750, field=f"chapter {i} instruction") for step in steps],
            "pitfalls": _text(item.get("pitfalls"), minimum=60, maximum=1100, field=f"chapter {i} pitfalls"),
            "citations": citations,
            "visuals": _visuals(item.get("frame_files"), visual),
        })
    if len(all_source_indices) < min(5, len(source)):
        raise LearningGuideError("The instructional chapters cite too little of the lecture.")
    step_list = examples.get("steps")
    if not isinstance(step_list, list) or len(step_list) < 3:
        raise LearningGuideError("Worked example must have at least three actionable steps.")
    result["worked_example"] = {
        "scenario": _text(examples.get("scenario"), minimum=75, maximum=1200, field="worked example scenario"),
        "steps": [_text(s, minimum=40, maximum=800, field="worked example step") for s in step_list[:12]],
        "expected_result": _text(examples.get("expected_result"), minimum=90, maximum=1200, field="worked example interpretation"),
        "limitations": _text(examples.get("limitations"), minimum=70, maximum=1000, field="worked example limitations"),
        "citations": _citations(examples.get("segment_ids"), source, "worked example"),
    }
    for i, item in enumerate(practice):
        if not isinstance(item, dict):
            raise LearningGuideError("Practice questions must include answers.")
        result["practice"].append({
            "question": _text(item.get("question"), minimum=35, maximum=550, field=f"exercise {i+1} question"),
            "model_answer": _text(item.get("model_answer"), minimum=85, maximum=1300, field=f"exercise {i+1} answer"),
            "citations": _citations(item.get("segment_ids"), source, f"exercise {i+1}"),
        })
    if visual and not any(chapter["visuals"] for chapter in result["chapters"]):
        raise LearningGuideError("Visual evidence was available but the guide ignored all slides/screenshots.")
    result["review_flags"] = [
        _text(flag, minimum=20, maximum=650, field="review flag")
        for flag in (raw.get("review_flags") or [])[:12]
    ]
    return result


def _model_response(prompt: str, model: str) -> dict[str, Any]:
    server = _endpoint()
    request = Request(
        server + "/api/generate",
        method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps({
            "model": model, "prompt": prompt, "format": "json", "stream": False,
            "options": {"temperature": 0.1, "num_ctx": 16384, "num_predict": 6000},
        }).encode("utf-8"),
    )
    try:
        with urlopen(request, timeout=360) as response:
            raw = json.loads(response.read(2_000_000))
        return json.loads(raw["response"])
    except (OSError, HTTPError, URLError, ValueError, KeyError) as exc:
        raise LearningGuideError(
            "Local Ollama generation failed. Verify Ollama is running, the configured "
            "CI_LEARNING_MODEL has been pulled, and CI_OLLAMA_URL is reachable. "
            f"Underlying error: {type(exc).__name__}"
        ) from exc


def generate_learning_guide(
    transcript: dict[str, Any], visual_manifest: dict[str, Any] | None,
    *, model: str | None = None, generator=None,
) -> dict[str, Any]:
    model = (model or learning_model()).strip()
    if not model:
        raise LearningGuideError(
            "A real learning model is not configured. Set CI_LEARNING_MODEL to an installed "
            "Ollama model (for example qwen2.5:7b), then restart Course Intelligence. "
            "The app will not substitute transcript excerpts for educational material."
        )
    if not re.fullmatch(r"[A-Za-z0-9_./:-]{2,100}", model):
        raise LearningGuideError("Invalid local model name.")
    ordered, source = _transcript_evidence(transcript)
    frames, available = _visual_evidence(visual_manifest)
    visible = "\n".join(
        f"[{item['segment_index']}] {item.get('start_ms')}ms: {item['text']}"
        for item in ordered
    )[:40000]
    frame_text = "\n".join(
        f"[{item['frame_file']}] {item.get('timestamp_ms')}ms "
        f"{item['category']}: {item['ocr']}" for item in frames
    )[:13500]
    prompt = (
        "You are a senior technical instructor. Build a COMPLETE, ORIGINAL learning module "
        "from the following authorized lecture evidence, NOT a seven-bullet video recap. "
        "Teach the WHY, WHAT, HOW, detailed steps, real demonstration, pitfalls, and diagnostic checks. "
        "Do not copy lecture passages verbatim; clarify terminology based on supplied visual text. "
        "Do not invent product controls, code, numbers, dates, savings, causal conclusions or capabilities. "
        "Separate DEMONSTRATED behavior from EXPLANATORY interpretation. "
        "If a figure is inconsistent, explicitly flag it. "
        "Use only provided segment indices and provided frame_file names as evidence IDs. "
        "Cite distinct relevant segment_ids for EVERY takeaway, chapter, worked example and answer. "
        "If visuals are supplied, cite relevant frame_files in chapters. "
        "Treat OCR as fallible and never claim code or diagram arrows were independently verified. "
        "Write 4-8 robust chapters when material supports them, each with explanation at least "
        "180 characters, why_it_matters at least 80 characters, 2+ useful detailed steps "
        "(40+ chars each), and pitfalls at least 60 characters. No filler like 'the instructor says'. "
        "Include at least four genuinely substantive takeaways, learner outcomes, a worked "
        "example with three steps and interpretation, and at least two answered exercises. "
        "Return JSON only with exactly this structure: "
        '{"title":"...","overview":"...","learning_outcomes":["..."],'
        '"takeaways":[{"text":"...","segment_ids":[1,2]}],'
        '"chapters":[{"heading":"...","explanation":"...","why_it_matters":"...",'
        '"steps":["...","..."],"pitfalls":"...","segment_ids":[3,4],'
        '"frame_files":["frames/periodic-0001.jpg"]}],'
        '"worked_example":{"scenario":"...","steps":["...","...","..."],'
        '"expected_result":"...","limitations":"...","segment_ids":[1,5]},'
        '"practice":[{"question":"...","model_answer":"...","segment_ids":[1,2]}],'
        '"review_flags":["..."]}. '
        "If no screenshot evidence is provided, use empty frame_files arrays. "
        "SOURCE TRANSCRIPT (each entry indexed for trusted citation):\n"
        f"{visible}\n\nVISUAL EVIDENCE (OCR is unverified; not a direct screenshot rendering):\n"
        f"{frame_text or 'None available'}\n"
    )
    responder = generator or _model_response
    response = responder(prompt, model)
    return validate_guide(response, transcript, source, available, model)
