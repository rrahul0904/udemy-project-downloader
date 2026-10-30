#!/usr/bin/env python3
"""Reddit video -> timestamped transcript and visual evidence intake POC.

Resolves one public/authorized Reddit post (including /r/.../s/... share URLs).
Does not bypass authentication, DRM, rate limits or copyrighted-platform controls.
Use --metadata-only to validate the actual source before moving to audio.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.transcript_export import export_transcript
from app.video_learning import export_learning_package, transcribe_with_local_whisper

MAX_MEDIA_BYTES = 2 * 1024 ** 3
MAX_DURATION_SECONDS = 4 * 60 * 60
MEDIA_SUFFIXES = {".mp4", ".webm", ".mkv", ".mov", ".m4v"}


class IntakeError(RuntimeError):
    pass


def validate_reddit_url(value: str) -> str:
    u = urlparse(value.strip())
    host = (u.hostname or "").lower().rstrip(".")
    if u.scheme != "https" or host not in {"reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com", "sh.reddit.com", "redd.it"}:
        raise ValueError("A public HTTPS Reddit video-post URL or share link is required.")
    if u.username or u.password or u.port not in {None, 443}:
        raise ValueError("Reddit URL must not contain credentials or a custom port.")
    path = u.path.rstrip("/")
    if host == "redd.it":
        valid = bool(re.fullmatch(r"/[A-Za-z0-9]{5,12}", path))
    else:
        valid = bool(re.fullmatch(r"/r/[A-Za-z0-9_]+/(?:s/[A-Za-z0-9]+|comments/[A-Za-z0-9]+(?:/[^/?#]*)?)", path))
    if not valid:
        raise ValueError("Expected /r/<community>/s/<share-id>, /r/<community>/comments/<post-id>, or redd.it/<post-id>.")
    return f"https://{host}{path}"


def _yt_options(folder: Path, *, metadata_only: bool) -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": metadata_only,
        "format": "bv*[height<=720]+ba/best[height<=720]/best",
        "merge_output_format": "mp4",
        "outtmpl": str(folder / "%(id)s.%(ext)s"),
        "max_filesize": MAX_MEDIA_BYTES,
        "socket_timeout": 20,
        "retries": 1,
        "fragment_retries": 1,
        "ignoreerrors": False,
    }


def _video_info(info: dict, url: str) -> dict:
    if not isinstance(info, dict) or info.get("_type") in {"playlist", "multi_video"}:
        raise IntakeError("Source is not one video. Please supply a direct Reddit video post URL.")
    extractor = str(info.get("extractor_key") or "")
    # In yt-dlp, a Reddit post with an external video can delegate extraction
    # to a different site; this POC intentionally does not silently archive it.
    if extractor != "Reddit":
        raise IntakeError(
            f"Reddit link did not resolve to a Reddit-hosted video (extractor: {extractor or 'unknown'}). "
            "Supply the original video URL or an authorized local MP4 instead."
        )
    formats = info.get("formats") or []
    has_video = any(
        isinstance(fmt, dict) and fmt.get("vcodec") not in {None, "none"}
        for fmt in formats
    ) or str(info.get("vcodec") or "none") != "none"
    if not has_video:
        raise IntakeError("Reddit post has no accessible video stream; text/images cannot be transcribed as audio.")
    duration = info.get("duration")
    if duration is not None and float(duration) > MAX_DURATION_SECONDS:
        raise IntakeError("Video exceeds 4-hour POC processing limit.")
    return {
        "status": "source_validated",
        "requested_url": url,
        "resolved_url": str(info.get("webpage_url") or url),
        "video_id": str(info.get("id") or ""),
        "title": str(info.get("title") or "Reddit video")[:220],
        "duration_seconds": duration,
        "extractor": extractor,
        "formats_available": len(formats),
        "video_stream_verified": True,
        "caption_status": "not_checked",
        "speech_status": "not_transcribed",
        "visual_status": "not_extracted",
    }


def resolve_reddit_video(url: str, folder: Path, *, metadata_only: bool = True) -> tuple[dict, Path | None]:
    """Access only the provided public Reddit link using yt-dlp's normal extractor."""
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    try:
        with YoutubeDL(_yt_options(folder, metadata_only=metadata_only)) as ydl:
            info = ydl.extract_info(url, download=not metadata_only)
            metadata = _video_info(info, url)
            path = Path(ydl.prepare_filename(info)) if not metadata_only else None
    except (DownloadError, OSError, ValueError) as exc:
        raise IntakeError(
            "Reddit video resolution failed. The short link may require Reddit's redirect "
            "or login, or the media may no longer be publicly available. "
            f"Underlying error: {type(exc).__name__}."
        ) from exc

    if path and not path.is_file():
        # yt-dlp may merge DASH video and separate audio into an MP4.
        candidates = [path.with_suffix(".mp4"), path.with_suffix(".mkv")]
        path = next((candidate for candidate in candidates if candidate.is_file()), path)
    if path and (not path.is_file() or path.stat().st_size > MAX_MEDIA_BYTES):
        raise IntakeError("Expected downloaded media missing or exceeds 2 GiB safety limit.")
    return metadata, path


def _output_folder(root: Path, url: str) -> Path:
    last = urlparse(url).path.rstrip("/").split("/")[-1]
    key = re.sub(r"[^a-zA-Z0-9_-]", "_", last)[:45]
    digest = hashlib.sha256(url.encode()).hexdigest()[:10]
    folder = root / "VideoToLearningPOC" / f"reddit-{key}-{digest}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One Reddit-hosted video -> real learning source evidence POC")
    parser.add_argument("--url", required=True, help="Reddit post or /r/community/s/share link")
    parser.add_argument("--metadata-only", action="store_true", help="Resolve video metadata; download/transcribe nothing")
    parser.add_argument("--media", type=Path, help="Authorized local media when Reddit shortlink cannot resolve")
    parser.add_argument("--asr-fallback", action="store_true", help="Run faster-whisper on the saved video")
    parser.add_argument("--asr-model", default="small")
    parser.add_argument("--language", default="en")
    parser.add_argument("--visuals", action="store_true", help="Extract sampled frames + OCR")
    parser.add_argument("--max-frames", type=int, default=48)
    parser.add_argument("--no-index", action="store_true")
    parser.add_argument("--download-root", type=Path, default=Path(os.getenv("DOWNLOAD_DIR", str(REPO / "downloads"))))
    parser.add_argument("--data-root", type=Path, default=Path(os.getenv("DATA_DIR", str(REPO / "data"))))
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?", args.language):
        parser.error("Invalid --language")
    try:
        url = validate_reddit_url(args.url)
        folder = _output_folder(args.download_root.resolve(), url)
        if args.media:
            if args.metadata_only:
                parser.error("--media cannot be combined with --metadata-only")
            media = args.media.resolve()
            if media.suffix.lower() not in MEDIA_SUFFIXES or not media.is_file() or media.stat().st_size > MAX_MEDIA_BYTES:
                raise IntakeError("--media must point to an existing authorized video no larger than 2 GiB.")
            # Keep the source and transcript together in the indexed downloads
            # folder. Never alter or delete the original authorized local file.
            if media.parent != folder.resolve():
                destination = folder / media.name
                if destination.exists() and destination.stat().st_size != media.stat().st_size:
                    raise IntakeError("A different video already occupies the local POC destination.")
                if not destination.exists():
                    shutil.copy2(media, destination)
                media = destination
            metadata = {
                "status": "local_media_source_url_unverified",
                "requested_url": url, "resolved_url": None,
                "video_id": media.stem, "title": media.stem,
                "speech_status": "not_transcribed",
                "visual_status": "not_extracted",
                "warning": "The local MP4 has NOT been verified as the Reddit linked video.",
            }
        else:
            metadata, media = resolve_reddit_video(url, folder, metadata_only=args.metadata_only)
        (folder / "source-intake.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        if args.metadata_only:
            print(json.dumps(metadata, indent=2))
            return 0
        if media is None:
            raise IntakeError("No audio/video content was acquired.")
        if not args.asr_fallback:
            raise IntakeError(
                "Media is present but the POC has not transcribed speech. "
                "Run with --asr-fallback on the transcript-worker; a metadata-only result is not a lesson."
            )
        from app.visual_learning import _duration_seconds, analyze_video_visuals
        duration = _duration_seconds(media)
        if duration <= 0 or duration > MAX_DURATION_SECONDS:
            raise IntakeError("Missing, invalid, or oversized video duration.")
        segments = transcribe_with_local_whisper(media, model=args.asr_model, language=args.language)
        if not segments:
            raise IntakeError("Local ASR returned no usable speech; refusing to fabricate a learning result.")
        # The transcript stays in the same folder as its source media, so
        # CourseStore can attach the correct media in the lesson viewer.
        target = media.parent / f"{media.stem}.{args.language}.vtt"
        body, _, _ = export_transcript({"segments": segments}, "vtt")
        target.write_text(body, encoding="utf-8")
        result = export_learning_package(
            target, title=metadata["title"], source_url=url,
            duration_ms=round(duration * 1000),
        )
        if args.visuals:
            visual_dir = Path(result["artifacts"]["quality_report"]).parent / "visuals"
            visual = analyze_video_visuals(media, visual_dir, max_frames=args.max_frames)
            result["visual"] = visual
            result["quality"]["visual_analysis"] = visual["status"]
            Path(result["artifacts"]["quality_report"]).write_text(
                json.dumps(result["quality"], indent=2), encoding="utf-8"
            )
        if not args.no_index:
            from app.database import CourseStore
            lib = CourseStore(args.data_root.resolve() / "app.db").sync_library(args.download_root.resolve())
            result["library"] = {"course_count": lib.get("course_count"), "lesson_count": lib.get("lesson_count")}
        result["source"] = metadata
        result["status"] = result["quality"]["status"]
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, IntakeError, RuntimeError, OSError) as exc:
        print(json.dumps({
            "status": "blocked", "source_url": args.url,
            "reason": str(exc)[:900],
            "next_step": "Use an accessible canonical Reddit post URL, or pass an authorized local MP4 "
                         "with --media and --asr-fallback. No learning content was invented.",
        }, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
