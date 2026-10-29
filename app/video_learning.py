"""Evidence-first, caption-first video-to-learning conversion.

The caption timeline is not proof of speech accuracy or visual completeness.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .learning_library import load_transcript
from .transcript_export import export_transcript


@dataclass(frozen=True)
class TranscriptQuality:
    status: str
    transcript_segments: int
    word_count: int
    timestamped_segments: int
    duration_ms: int | None
    caption_coverage_ratio: float | None
    non_captioned_ms: int | None
    invalid_timing_segments: int
    duplicate_segments: int
    gap_count_over_30s: int
    warnings: list[str]
    visual_analysis: str = "not_performed"
    asr_cross_check: str = "not_performed"


def _ms(value: Any) -> int | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        number = float(value)
        return int(number) if math.isfinite(number) and number >= 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def transcript_quality(transcript: dict[str, Any], duration_ms: int | None = None) -> TranscriptQuality:
    segments = transcript.get("segments") or []
    duration = _ms(duration_ms)
    ranges: list[tuple[int, int]] = []
    invalid = duplicates = words = 0
    previous = None
    for segment in segments:
        body = re.sub(r"\s+", " ", str(segment.get("text") or "")).strip()
        words += len(re.findall(r"\b\w+\b", body))
        start = _ms(segment.get("start_ms", segment.get("start")))
        end = _ms(segment.get("end_ms", segment.get("end")))
        key = (start, end, body)
        duplicates += int(key == previous)
        previous = key
        if start is None and end is None:
            continue
        if start is None or end is None or end <= start or (duration is not None and start >= duration):
            invalid += 1
        else:
            ranges.append((start, min(end, duration) if duration is not None else end))
    merged: list[list[int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    coverage = sum(end - start for start, end in merged)
    gaps = 0
    prev = 0
    for start, end in merged:
        gaps += int(start - prev > 30000)
        prev = end
    if duration is not None:
        gaps += int(duration - prev > 30000)
    ratio = round(min(1, coverage / duration), 4) if duration else None
    remaining = max(0, duration - coverage) if duration is not None else None
    warnings = []
    if not segments or not words:
        warnings.append("No spoken content recovered; conversion cannot be approved.")
    if not ranges:
        warnings.append("No valid timestamps available.")
    if duration is None:
        warnings.append("Media duration unavailable; total coverage unverified.")
    if invalid:
        warnings.append(f"{invalid} malformed caption timestamps require review.")
    if duplicates:
        warnings.append(f"{duplicates} adjacent duplicate segments require review.")
    if gaps:
        warnings.append(f"{gaps} caption gaps over 30s may represent silence or missing speech.")
    warnings.append("Caption coverage does NOT measure word accuracy or capture on-screen slides/code.")
    return TranscriptQuality(
        status="transcribed_unverified" if segments and words and ranges and not invalid else "needs_review",
        transcript_segments=len(segments), word_count=words, timestamped_segments=len(ranges),
        duration_ms=duration, caption_coverage_ratio=ratio, non_captioned_ms=remaining,
        invalid_timing_segments=invalid, duplicate_segments=duplicates,
        gap_count_over_30s=gaps, warnings=warnings,
    )


def _timestamp(milliseconds: Any) -> str:
    ms = _ms(milliseconds)
    if ms is None:
        return "untimed"
    hours, remaining = divmod(ms // 1000, 3600)
    minutes, seconds = divmod(remaining, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def extractive_learning_guide(transcript: dict[str, Any], title: str, source_url: str) -> str:
    """Lossless excerpt outline. Never invent facts or claim full instructional synthesis."""
    rows = [
        f"# {re.sub(r'[\r\n]+', ' ', title)}", "",
        "## Evidence and limitations", "",
        f"- Source: {source_url or 'local authorized source'}",
        "- Exact transcript excerpts, not a verified AI-written course.",
        "- Speech fidelity and visual slides/diagrams/code still require review.", "",
    ]
    segments = [s for s in transcript.get("segments") or [] if str(s.get("text") or "").strip()]
    if not segments:
        return "\n".join(rows + ["## Incomplete", "", "No usable transcript segments.", ""])
    for start in range(0, len(segments), 12):
        subset = segments[start:start + 12]
        begin = _timestamp(subset[0].get("start_ms", subset[0].get("start")))
        end = _timestamp(subset[-1].get("end_ms", subset[-1].get("end")))
        rows.extend([f"## Transcript section {start // 12 + 1} ({begin}–{end})", ""])
        for s in subset:
            stamp = _timestamp(s.get("start_ms", s.get("start")))
            body = re.sub(r"\s+", " ", str(s["text"])).strip()
            rows.append(f"- **[{stamp}]** {body}")
        rows.append("")
    return "\n".join(rows)


def export_learning_package(path: Path, *, title: str, source_url: str, duration_ms: int | None) -> dict[str, Any]:
    """Export to a hidden directory so CourseStore does not re-ingest exports as lessons."""
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    parsed = load_transcript(path.parent, path.name)
    transcript = {"segments": [
        {"segment_index": index, "start_ms": s.get("start"), "end_ms": s.get("end"), "text": s.get("text", "")}
        for index, s in enumerate(parsed["segments"])
    ]}
    q = transcript_quality(transcript, duration_ms)
    out = path.parent / ("." + path.stem + ".learning")
    out.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for fmt in ("txt", "json", "srt", "vtt"):
        if fmt in ("srt", "vtt") and (q.timestamped_segments != q.transcript_segments or q.invalid_timing_segments):
            continue
        body, _, ext = export_transcript(transcript, fmt)
        item = out / ("transcript." + ext)
        item.write_text(body, encoding="utf-8")
        artifacts[fmt] = str(item)
    notes = out / "source-grounded-study-guide.md"
    notes.write_text(extractive_learning_guide(transcript, title, source_url), encoding="utf-8")
    report = out / "quality-report.json"
    report.write_text(json.dumps(asdict(q), indent=2), encoding="utf-8")
    artifacts["study_guide"] = str(notes)
    artifacts["quality_report"] = str(report)
    return {"source_transcript": str(path), "quality": asdict(q), "artifacts": artifacts}


def transcribe_with_local_whisper(media_path: Path, *, model: str = "small", language: str | None = None) -> list[dict[str, Any]]:
    """Optional CPU speech recognition; no remote ASR service."""
    path = Path(media_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() not in {".mp4", ".webm", ".mkv", ".mov", ".mp3", ".m4a", ".wav"}:
        raise ValueError("Unsupported media file format")
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Install optional requirements-asr.txt for --asr-fallback") from exc
    model_engine = WhisperModel(model, device="cpu", compute_type="int8")
    results, _ = model_engine.transcribe(str(path), language=language, vad_filter=True)
    return [
        {"start_ms": round(s.start * 1000), "end_ms": round(s.end * 1000), "text": s.text.strip()}
        for s in results if s.text.strip()
    ]
