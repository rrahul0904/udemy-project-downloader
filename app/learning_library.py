from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any

TRANSCRIPT_EXTENSIONS = {".vtt", ".srt", ".txt", ".md", ".json3"}
MEDIA_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".mp3", ".m4a", ".wav"}
TIMED_EXTENSIONS = {".vtt", ".srt", ".json3"}


def build_library(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    courses: dict[str, dict[str, Any]] = {}

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if path.suffix.lower() not in TRANSCRIPT_EXTENSIONS:
            continue

        course_key = rel.parts[0] if len(rel.parts) > 1 else "Ungrouped"
        course = courses.setdefault(
            course_key,
            {
                "id": _stable_id(course_key),
                "title": _humanize(course_key),
                "directory": course_key,
                "lessons": [],
            },
        )
        media = _find_matching_media(path)
        lesson = {
            "id": _stable_id(rel.as_posix()),
            "title": _lesson_title(path),
            "transcript_path": rel.as_posix(),
            "transcript_format": path.suffix.lower().lstrip("."),
            "language": _infer_language(path),
            "size": path.stat().st_size,
            "media_path": media.relative_to(root).as_posix() if media else None,
        }
        course["lessons"].append(lesson)

    result = []
    for course in courses.values():
        course["lessons"].sort(key=lambda item: item["transcript_path"].lower())
        course["lesson_count"] = len(course["lessons"])
        result.append(course)
    result.sort(key=lambda item: item["title"].lower())

    return {
        "courses": result,
        "course_count": len(result),
        "lesson_count": sum(item["lesson_count"] for item in result),
    }


def load_transcript(root: Path, relative_path: str) -> dict[str, Any]:
    path = _resolve_file(root, relative_path)
    if path.suffix.lower() not in TRANSCRIPT_EXTENSIONS:
        raise ValueError("Unsupported transcript format.")

    suffix = path.suffix.lower()
    if suffix == ".vtt":
        segments = _parse_vtt(path.read_text(encoding="utf-8", errors="replace"))
    elif suffix == ".srt":
        segments = _parse_srt(path.read_text(encoding="utf-8", errors="replace"))
    elif suffix == ".json3":
        segments = _parse_json3(path.read_text(encoding="utf-8", errors="replace"))
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
        segments = [{"start": None, "end": None, "text": text.strip()}] if text.strip() else []

    text = "\n".join(segment["text"] for segment in segments if segment["text"]).strip()
    return {
        "path": relative_path,
        "format": suffix.lstrip("."),
        "has_timestamps": suffix in TIMED_EXTENSIONS,
        "text": text,
        "word_count": len(re.findall(r"\b\w+\b", text)),
        "segments": segments,
    }


def search_transcript(root: Path, relative_path: str, query: str, limit: int = 50) -> dict[str, Any]:
    query = query.strip()
    if not query:
        return {"query": query, "hits": []}

    transcript = load_transcript(root, relative_path)
    needle = query.casefold()
    hits = []
    for index, segment in enumerate(transcript["segments"]):
        if needle not in segment["text"].casefold():
            continue
        hits.append({"index": index, **segment})
        if len(hits) >= max(1, min(limit, 200)):
            break
    return {"query": query, "hits": hits, "count": len(hits)}


def _resolve_file(root: Path, relative_path: str) -> Path:
    target = (root / relative_path).resolve()
    root = root.resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("Transcript path is outside the download directory.") from exc
    if not target.is_file():
        raise FileNotFoundError(relative_path)
    return target


def _find_matching_media(transcript: Path) -> Path | None:
    stem = transcript.name
    for suffix in (".vtt", ".srt", ".json3", ".txt", ".md"):
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    stem = re.sub(r"\.[a-z]{2,3}(?:-[A-Za-z]{2,4})?$", "", stem)
    candidates = []
    for sibling in transcript.parent.iterdir():
        if not sibling.is_file() or sibling.suffix.lower() not in MEDIA_EXTENSIONS:
            continue
        if sibling.stem == stem or sibling.stem.startswith(stem) or stem.startswith(sibling.stem):
            candidates.append(sibling)
    return sorted(candidates)[0] if candidates else None


def _parse_vtt(text: str) -> list[dict[str, Any]]:
    text = text.replace("\r\n", "\n")
    blocks = re.split(r"\n\s*\n", text)
    segments = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            continue
        timing = lines[timing_index]
        start_raw, end_raw = [part.strip().split()[0] for part in timing.split("-->", 1)]
        body = " ".join(lines[timing_index + 1 :])
        body = re.sub(r"<[^>]+>", "", html.unescape(body)).strip()
        if body:
            segments.append({"start": _timestamp_ms(start_raw), "end": _timestamp_ms(end_raw), "text": body})
    return _dedupe_adjacent(segments)


def _parse_srt(text: str) -> list[dict[str, Any]]:
    text = text.replace("\r\n", "\n")
    blocks = re.split(r"\n\s*\n", text)
    segments = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            continue
        start_raw, end_raw = [part.strip() for part in lines[timing_index].split("-->", 1)]
        body = " ".join(lines[timing_index + 1 :])
        body = re.sub(r"<[^>]+>", "", html.unescape(body)).strip()
        if body:
            segments.append({"start": _timestamp_ms(start_raw), "end": _timestamp_ms(end_raw), "text": body})
    return _dedupe_adjacent(segments)


def _parse_json3(text: str) -> list[dict[str, Any]]:
    payload = json.loads(text)
    segments = []
    for event in payload.get("events", []):
        chunks = event.get("segs") or []
        body = "".join(chunk.get("utf8", "") for chunk in chunks).replace("\n", " ").strip()
        if not body:
            continue
        start = int(event.get("tStartMs", 0))
        duration = int(event.get("dDurationMs", 0))
        segments.append({"start": start, "end": start + duration, "text": body})
    return _dedupe_adjacent(segments)


def _dedupe_adjacent(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    previous = None
    for segment in segments:
        normalized = re.sub(r"\s+", " ", segment["text"]).strip()
        if not normalized or normalized == previous:
            continue
        output.append({**segment, "text": normalized})
        previous = normalized
    return output


def _timestamp_ms(value: str) -> int:
    value = value.strip().replace(",", ".")
    parts = value.split(":")
    try:
        if len(parts) == 3:
            hours, minutes, seconds = parts
        elif len(parts) == 2:
            hours = "0"
            minutes, seconds = parts
        else:
            return 0
        return int((int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1000)
    except ValueError:
        return 0


def _infer_language(path: Path) -> str | None:
    parts = path.name.split(".")
    if len(parts) >= 3:
        candidate = parts[-2]
        if re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?", candidate):
            return candidate
    return None


def _lesson_title(path: Path) -> str:
    name = path.name
    for suffix in (".vtt", ".srt", ".json3", ".txt", ".md"):
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
            break
    name = re.sub(r"\.[a-z]{2,3}(?:-[A-Za-z]{2,4})?$", "", name)
    return _humanize(name)


def _humanize(value: str) -> str:
    value = re.sub(r"[-_]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or "Untitled"


def _stable_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]
