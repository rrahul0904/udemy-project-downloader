"""Bounded visual evidence extraction for authorized lecture videos.

Preserve frame images and timestamps. OCR and optional local vision descriptions
are NOT guaranteed accurate and are never silently treated as verified code.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

VIDEO_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov", ".m4v"}
MAX_VIDEO_BYTES = 2 * 1024**3
SCENE_TIMES = re.compile(r"\bpts_time:([-+0-9.]+)")
CODE_SIGNALS = re.compile(
    r"\b(?:def\s+\w+|class\s+\w+|import\s+\w+|from\s+\w+\s+import|"
    r"SELECT\b|FROM\b|WHERE\b|JOIN\b|CREATE\s+TABLE|INSERT\s+INTO|"
    r"pip\s+install|docker\s+run|terraform\s+\{|resource\s+\"|"
    r"const\s+\w+|function\s+\w+|public\s+static|console\.log|"
    r"print\s*\(|\breturn\b|\bif\s*\(|\bfor\s*\()", re.I
)
DIAGRAM_SIGNALS = re.compile(
    r"\b(architecture|data\s*flow|pipeline|network\s*diagram|workflow|flowchart|topology)\b|[→←↔⟶]|-->", re.I
)


def _exec(args: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Video processing exceeded {timeout}s timeout") from exc
    if result.returncode:
        raise RuntimeError(f"{Path(args[0]).name} failed: {result.stderr[-1000:]}")
    return result


def _duration_seconds(path: Path) -> float:
    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe is required for visual analysis")
    output = _exec(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", str(path)], timeout=30).stdout.strip()
    try:
        seconds = float(output)
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("Invalid duration")
        return seconds
    except ValueError as exc:
        raise RuntimeError("Could not determine positive video duration") from exc


def _ocr_image(frame: Path) -> dict[str, Any]:
    """Run Tesseract TSV and group detected words into visible lines."""
    if not shutil.which("tesseract"):
        return {"status": "unavailable", "text": "", "confidence": None, "line_count": 0}
    output = _exec(["tesseract", str(frame), "stdout", "--psm", "11", "tsv"], timeout=45).stdout
    lines: dict[tuple[str, ...], list[tuple[int, str, float]]] = {}
    for item in csv.DictReader(io.StringIO(output), delimiter="\t"):
        word = (item.get("text") or "").strip()
        if not word:
            continue
        try:
            confidence = float(item.get("conf", "-1"))
            left = int(item.get("left", "0"))
        except (ValueError, TypeError):
            continue
        if confidence < 35:
            continue
        key = tuple(item.get(k, "") for k in ("page_num", "block_num", "par_num", "line_num"))
        lines.setdefault(key, []).append((left, word, confidence))
    ordered = [sorted(words) for words in lines.values()]
    text = "\n".join(" ".join(part[1] for part in line) for line in ordered)
    scores = [part[2] for line in ordered for part in line]
    return {"status": "completed", "text": text,
            "confidence": round(sum(scores) / len(scores), 1) if scores else None,
            "line_count": len(ordered)}


def _classify(text: str) -> str:
    if not text.strip():
        return "unclassified_visual"
    matches = CODE_SIGNALS.findall(text)
    if len(matches) >= 2 or re.search(r"\bSELECT\b[\s\S]*\bFROM\b", text, re.I):
        return "code_candidate"
    if DIAGRAM_SIGNALS.search(text):
        return "diagram_candidate"
    if len(text.split()) >= 5:
        return "slide_candidate"
    return "unclassified_visual"


def _local_vision_description(frame: Path, model: str) -> str:
    """Opt-in local Ollama only, never a remote media/image API."""
    if not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,80}", model):
        raise ValueError("Invalid Ollama model name")
    prompt = (
        "Describe ONLY visible content in this lecture frame. Extract any visible code with lines, "
        "slide headings, diagram boxes, readable labels and arrow directions. If relationships or "
        "characters are unclear, say unreadable or uncertain rather than inventing them. "
        "Do not infer anything about other frames. Keep the description concise."
    )
    payload = json.dumps({
        "model": model, "prompt": prompt,
        "images": [base64.b64encode(frame.read_bytes()).decode("ascii")],
        "stream": False,
    }).encode("utf-8")
    req = Request("http://127.0.0.1:11434/api/generate", data=payload,
                  headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=120) as response:
        answer = json.loads(response.read(1024 * 1024))
    return str(answer.get("response") or "").strip()[:8000]


def _periodic_frames(media: Path, frames: Path, duration: float, limit: int) -> list[dict[str, Any]]:
    interval = max(8.0, duration / max(1, limit))
    _exec(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
           "-i", str(media), "-vf",
           f"fps=fps=1/{interval:.6f}:round=up,scale=1280:-2",
           "-q:v", "3", "-frames:v", str(limit),
           str(frames / "periodic-%04d.jpg")], timeout=600)
    return [{"file": p, "time_ms": int(index * interval * 1000), "selection": "periodic"}
            for index, p in enumerate(sorted(frames.glob("periodic-*.jpg")))]


def _scene_frames(media: Path, frames: Path, limit: int) -> list[dict[str, Any]]:
    if not limit:
        return []
    args = ["ffmpeg", "-hide_banner", "-loglevel", "info", "-nostdin", "-y",
            "-i", str(media), "-vf",
            r"select=gt(scene\,0.36),showinfo,scale=1280:-2",
            "-vsync", "vfr", "-q:v", "3", "-frames:v", str(limit),
            str(frames / "scene-%04d.jpg")]
    try:
        result = _exec(args, timeout=600)
    except RuntimeError as exc:
        # ffmpeg may return nonzero when no scene passed the threshold.
        if "Nothing was written" in str(exc) or "Could not open encoder before EOF" in str(exc):
            return []
        raise
    times = [max(0.0, float(t)) for t in SCENE_TIMES.findall(result.stderr)]
    items = sorted(frames.glob("scene-*.jpg"))
    return [{"file": p, "time_ms": round(times[index] * 1000) if index < len(times) else None,
             "selection": "scene"} for index, p in enumerate(items)]


def _render_visual_notes(items: list[dict[str, Any]], source: str) -> str:
    rows = ["# Visual evidence from the lecture", "", f"Source: {source}", "",
            "Frames are sampled, not exhaustive. OCR may misread code or slide text.",
            "Diagrams are preserved as images; arrows/relationships are NOT verified by OCR.",
            "Optional local-model descriptions are **unverified**.", ""]
    for index, item in enumerate(items, 1):
        stamp = "unknown" if item["timestamp_ms"] is None else f"{item['timestamp_ms'] / 1000:.1f}s"
        rows.extend([f"## Frame {index} — {stamp} — {item['category']}", "",
                     f"![Frame {index}]({item['frame_file']})", ""])
        if item["ocr"]["text"]:
            label = ("Unverified on-screen code OCR" if item["category"] == "code_candidate"
                     else "Unverified text OCR")
            rows.extend([f"**{label}:**", "", "~~~text", item["ocr"]["text"], "~~~", ""])
        if item["vision_description"]:
            rows.extend(["**Optional local visual-model description (unverified):**", "",
                         item["vision_description"], ""])
        if not item["ocr"]["text"] and not item["vision_description"]:
            rows.extend(["No readable text extracted; inspect frame manually.", ""])
    return "\n".join(rows)


def analyze_video_visuals(
    media_path: Path, output_dir: Path, *, max_frames: int = 48,
    vision_model: str | None = None,
) -> dict[str, Any]:
    """Export sampled video frames and unverified OCR/diagram/code evidence."""
    media = Path(media_path).resolve()
    if not media.is_file() or media.suffix.lower() not in VIDEO_SUFFIXES:
        raise ValueError("Provide an existing authorized MP4/MKV/WebM/MOV/M4V video file")
    if media.stat().st_size > MAX_VIDEO_BYTES:
        raise ValueError("Video exceeds the 2 GiB POC safety cap")
    if max_frames < 2 or max_frames > 120:
        raise ValueError("max_frames must be between 2 and 120")
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required for visual extraction")
    duration = _duration_seconds(media)
    if duration > 4 * 3600:
        raise ValueError("Video exceeds the four-hour POC limit")
    destination = Path(output_dir).resolve()
    if destination == media.parent or destination in media.parents:
        raise ValueError("Visual output must be a separate subdirectory")
    frames = destination / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    for glob in ("periodic-*.jpg", "scene-*.jpg"):
        for stale in frames.glob(glob):
            stale.unlink()
    periodic_limit = max(1, max_frames * 2 // 3)
    candidates = _periodic_frames(media, frames, duration, periodic_limit)
    candidates += _scene_frames(media, frames, max_frames - len(candidates))
    candidates.sort(key=lambda item: (item["time_ms"] is None, item["time_ms"] or 0, str(item["file"])))
    results = []
    seen: set[str] = set()
    warnings = []
    if not shutil.which("tesseract"):
        warnings.append("Tesseract OCR unavailable: only frame images were extracted.")
    if not candidates:
        warnings.append("No frames could be extracted from this video.")
    for frame in candidates[:max_frames]:
        ocr = _ocr_image(frame["file"])
        category = _classify(ocr["text"])
        digest = hashlib.sha256(frame["file"].read_bytes()).hexdigest()
        # Matching OCR can hide differing diagrams; de-duplicate only exact images.
        if digest in seen:
            frame["file"].unlink(missing_ok=True)
            continue
        seen.add(digest)
        description = None
        if vision_model:
            try:
                description = _local_vision_description(frame["file"], vision_model)
            except (OSError, ValueError, RuntimeError, TimeoutError, KeyError) as exc:
                warnings.append(f"Vision model could not analyze {frame['file'].name}: {type(exc).__name__}")
        results.append({
            "timestamp_ms": frame["time_ms"], "frame_file": "frames/" + frame["file"].name,
            "selection": frame["selection"], "category": category, "ocr": ocr,
            "vision_description": description,
            "vision_review": "unverified" if description else "not_performed",
            "sha256": digest,
        })
    status = "frames_with_ocr_unverified" if shutil.which("tesseract") else "frames_only_unverified"
    if not results:
        status = "needs_review"
    elif shutil.which("tesseract") and not any(item["ocr"]["text"] for item in results):
        warnings.append("OCR processed frames but no legible text was recovered.")
    manifest = {
        "status": status, "source_media_name": media.name, "duration_ms": round(duration * 1000),
        "frames_examined": len(results),
        "sampling": {"periodic": True, "scene_change": True, "max_frames": max_frames},
        "warning": "Sampling and OCR do not prove complete or correct visual understanding.",
        "warnings": warnings, "items": results,
    }
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "visual-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (destination / "visual-study-notes.md").write_text(_render_visual_notes(results, media.name), encoding="utf-8")
    for name, category in (("code-candidates", "code_candidate"),
                           ("slide-candidates", "slide_candidate"),
                           ("diagram-candidates", "diagram_candidate")):
        (destination / f"{name}.md").write_text(_render_visual_notes(
            [item for item in results if item["category"] == category], media.name), encoding="utf-8")
    return {key: value for key, value in manifest.items() if key != "items"} | {
        "manifest": str(destination / "visual-manifest.json"),
        "visual_notes": str(destination / "visual-study-notes.md"),
        "code_candidates": str(destination / "code-candidates.md"),
        "slide_candidates": str(destination / "slide-candidates.md"),
        "diagram_candidates": str(destination / "diagram-candidates.md"),
    }
