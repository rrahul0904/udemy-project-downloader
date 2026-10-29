#!/usr/bin/env python3
"""Single YouTube-video/authorized local transcript to Course Intelligence POC."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.transcript_export import export_transcript
from app.video_learning import export_learning_package, transcribe_with_local_whisper

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def normalize_youtube_url(raw: str) -> tuple[str, str]:
    u = urlparse(raw)
    host = (u.hostname or "").lower().rstrip(".")
    if u.scheme != "https" or host not in {"www.youtube.com", "youtube.com", "m.youtube.com", "youtu.be"}:
        raise ValueError("Use a supported HTTPS YouTube video URL.")
    if host == "youtu.be":
        video_id = u.path.strip("/")
    elif u.path == "/watch":
        video_id = (parse_qs(u.query).get("v") or [""])[0]
    elif u.path.startswith("/shorts/"):
        video_id = u.path.split("/")[2]
    else:
        raise ValueError("Expected one watch, Shorts, or youtu.be video.")
    if not VIDEO_ID.fullmatch(video_id):
        raise ValueError("Invalid YouTube video identifier.")
    return f"https://www.youtube.com/watch?v={video_id}", video_id


def find_caption(directory: Path, video_id: str, language: str) -> Path | None:
    files = [p for ext in ("vtt", "srt", "json3") for p in directory.glob(f"{video_id}.*.{ext}") if p.is_file()]
    if not files:
        return None
    def priority(p: Path) -> tuple[int, int, str]:
        name = p.name.lower()
        lang = language.lower()
        preference = 0 if name.startswith(f"{video_id.lower()}.{lang}.") else 1 if name.startswith(f"{video_id.lower()}.en.") else 2
        return preference, 0 if p.suffix == ".vtt" else 1, name
    return sorted(files, key=priority)[0]


def download_caption(url: str, target: Path, video_id: str, language: str) -> dict:
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError("Install requirements.txt for yt-dlp acquisition.") from exc
    with YoutubeDL({
        "skip_download": True, "noplaylist": True,
        "writesubtitles": True, "writeautomaticsub": True,
        "subtitleslangs": [language], "subtitlesformat": "vtt/best",
        "writeinfojson": True, "outtmpl": str(target / "%(id)s.%(ext)s"), "quiet": True,
    }) as ydl:
        info = ydl.extract_info(url, download=True)
    if not isinstance(info, dict) or info.get("_type") in {"playlist", "multi_video"} or str(info.get("id")) != video_id:
        raise RuntimeError("Unexpected YouTube media; refusing playlist or mismatched video.")
    return info


def local_asr(url: str, folder: Path, video_id: str, language: str, model: str) -> Path | None:
    from yt_dlp import YoutubeDL
    # Authenticated/private/DRM sources are not bypassed. Only ordinarily accessible media.
    with YoutubeDL({
        "noplaylist": True, "format": "bestaudio/best",
        "outtmpl": str(folder / "%(id)s.%(ext)s"),
        "max_filesize": 1024 * 1024 * 1024,
        "quiet": True,
    }) as ydl:
        info = ydl.extract_info(url, download=True)
        if not isinstance(info, dict) or str(info.get("id")) != video_id:
            raise RuntimeError("Unexpected YouTube media during ASR.")
        audio_path = Path(ydl.prepare_filename(info))
    segments = transcribe_with_local_whisper(audio_path, model=model, language=language)
    if not segments:
        return None
    body, _, _ = export_transcript({"segments": segments}, "vtt")
    dest = folder / f"{video_id}.{language}.vtt"
    dest.write_text(body, encoding="utf-8")
    return dest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Evidence-first video-to-learning pilot")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="Single YouTube URL; playlist query intentionally ignored")
    src.add_argument("--input", type=Path, help="Local authorized VTT/SRT/JSON3/TXT/MD")
    ap.add_argument("--source-url", default="")
    ap.add_argument("--download-root", type=Path, default=REPO / "downloads")
    ap.add_argument("--data-root", type=Path, default=REPO / "data")
    ap.add_argument("--language", default="en")
    ap.add_argument("--asr-fallback", action="store_true")
    ap.add_argument("--asr-model", default="small")
    ap.add_argument("--duration-seconds", type=float, default=None)
    ap.add_argument("--no-index", action="store_true")
    args = ap.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?", args.language):
        ap.error("Invalid --language.")
    root = args.download_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if args.input:
        existing = args.input.resolve()
        if not existing.is_file() or existing.suffix.lower() not in {".vtt", ".srt", ".json3", ".txt", ".md"}:
            ap.error("--input requires an existing supported transcript.")
        folder = root / "VideoToLearningPOC" / "local"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / existing.name
        if existing != path:
            shutil.copyfile(existing, path)
        title, url = existing.stem, args.source_url
        duration = round(args.duration_seconds * 1000) if args.duration_seconds and args.duration_seconds > 0 else None
    else:
        try:
            url, video_id = normalize_youtube_url(args.url)
        except ValueError as exc:
            ap.error(str(exc))
        folder = root / "VideoToLearningPOC" / video_id
        folder.mkdir(parents=True, exist_ok=True)
        info = download_caption(url, folder, video_id, args.language)
        path = find_caption(folder, video_id, args.language)
        title = str(info.get("title") or video_id)
        duration = round(float(info["duration"]) * 1000) if info.get("duration") else None
        if path is None and args.asr_fallback:
            path = local_asr(url, folder, video_id, args.language, args.asr_model)
        if path is None:
            print(json.dumps({"status": "blocked", "video_id": video_id, "reason": "No accessible captions. Optional local ASR requires --asr-fallback."}, indent=2))
            return 2
    result = export_learning_package(path, title=title, source_url=url, duration_ms=duration)
    if not result["quality"]["word_count"]:
        print(json.dumps({"status": "blocked", "reason": "Zero usable transcript words.", **result}, indent=2))
        return 2
    if not args.no_index:
        from app.database import CourseStore
        library = CourseStore(args.data_root.resolve() / "app.db").sync_library(root)
        result["library"] = {"course_count": library.get("course_count"), "lesson_count": library.get("lesson_count")}
    print(json.dumps({"status": result["quality"]["status"], **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
