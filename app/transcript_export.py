from __future__ import annotations

import json
from typing import Any

SUPPORTED_EXPORT_FORMATS = {"txt", "json", "srt", "vtt"}


def export_transcript(transcript: dict[str, Any], output_format: str) -> tuple[str, str, str]:
    """Return deterministic transcript text, media type, and file extension."""
    output_format = output_format.strip().lower()
    if output_format not in SUPPORTED_EXPORT_FORMATS:
        raise ValueError("Unsupported transcript export format.")

    segments = transcript.get("segments") or []
    if output_format == "txt":
        body = "\n".join(str(segment.get("text") or "").strip() for segment in segments).strip()
        return (body + ("\n" if body else ""), "text/plain; charset=utf-8", "txt")

    if output_format == "json":
        payload = {
            "id": transcript.get("id"),
            "lesson_id": transcript.get("lesson_id"),
            "language": transcript.get("language"),
            "source_kind": transcript.get("source_kind"),
            "version": transcript.get("version"),
            "provenance": transcript.get("provenance") or {},
            "segments": [
                {
                    "index": segment.get("segment_index", index),
                    "start_ms": segment.get("start_ms"),
                    "end_ms": segment.get("end_ms"),
                    "text": segment.get("text") or "",
                }
                for index, segment in enumerate(segments)
            ],
        }
        return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", "application/json; charset=utf-8", "json")

    timed = [segment for segment in segments if segment.get("start_ms") is not None and segment.get("end_ms") is not None]
    if len(timed) != len(segments) or not timed:
        raise ValueError("SRT/VTT export requires timestamped transcript segments.")

    if output_format == "srt":
        blocks = []
        for index, segment in enumerate(timed, start=1):
            blocks.append(
                f"{index}\n{_format_timestamp(segment['start_ms'], comma=True)} --> {_format_timestamp(segment['end_ms'], comma=True)}\n{segment['text']}"
            )
        return ("\n\n".join(blocks) + "\n", "application/x-subrip; charset=utf-8", "srt")

    blocks = ["WEBVTT"]
    for segment in timed:
        blocks.append(
            f"{_format_timestamp(segment['start_ms'])} --> {_format_timestamp(segment['end_ms'])}\n{segment['text']}"
        )
    return ("\n\n".join(blocks) + "\n", "text/vtt; charset=utf-8", "vtt")


def _format_timestamp(value_ms: int, *, comma: bool = False) -> str:
    value_ms = max(0, int(value_ms))
    hours, remainder = divmod(value_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    separator = "," if comma else "."
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{milliseconds:03d}"
