from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse, urlunparse

from .media_sources import MediaSourceError, detect_media_source


class UrlValidationError(ValueError):
    """Raised when a submitted URL is outside the supported download scope."""


@dataclass(frozen=True)
class NormalizedUrl:
    url: str
    platform: str


YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}


def normalize_supported_url(value: str) -> NormalizedUrl:
    url = (value or "").strip()
    try:
        detected = detect_media_source(url)
    except MediaSourceError as exc:
        raise UrlValidationError(str(exc)) from exc

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    platform = detected.source.key

    if platform == "udemy":
        if not parsed.path or parsed.path == "/":
            raise UrlValidationError("Paste a specific Udemy course URL.")
        return NormalizedUrl(_normalize_parsed_url(parsed), platform)

    if platform == "youtube":
        if not _is_specific_youtube_url(parsed):
            raise UrlValidationError("Paste a specific YouTube video, Shorts, live, or playlist URL.")
        return NormalizedUrl(_normalize_parsed_url(parsed), platform)

    if not detected.source.archive_enabled:
        raise UrlValidationError(
            f"{detected.source.display_name} is recognized but its archive adapter is not enabled yet."
        )

    if not _is_specific_public_item(platform, host, parsed):
        raise UrlValidationError(
            f"Paste a specific {detected.source.display_name} post, clip, video, pin, recording, or episode URL rather than a profile or feed."
        )

    return NormalizedUrl(_normalize_parsed_url(parsed), platform)


def normalize_udemy_url(value: str) -> str:
    normalized = normalize_supported_url(value)
    if normalized.platform != "udemy":
        raise UrlValidationError("Paste a specific Udemy course URL.")
    return normalized.url


def slug_from_url(value: str) -> str:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    parts = [part for part in parsed.path.split("/") if part]

    if host in YOUTUBE_HOSTS:
        query = parse_qs(parsed.query)
        if host == "youtu.be" and parts:
            candidate = parts[0]
        elif parts[:1] == ["watch"] and query.get("v"):
            candidate = query["v"][0]
        elif parts[:1] == ["playlist"] and query.get("list"):
            candidate = query["list"][0]
        elif parts[:1] in (["shorts"], ["embed"], ["live"]) and len(parts) >= 2:
            candidate = parts[1]
        elif query.get("list"):
            candidate = query["list"][0]
        else:
            candidate = "youtube"
    elif _is_udemy_host(host) and "course" in parts:
        index = parts.index("course")
        candidate = parts[index + 1] if len(parts) > index + 1 else "udemy-course"
    else:
        candidate = parts[-1] if parts else parsed.hostname or "media"

    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in candidate)
    safe = "-".join(part for part in safe.split("-") if part)
    return safe[:80] or "media"


def _is_udemy_host(host: str) -> bool:
    return host == "udemy.com" or host.endswith(".udemy.com")


def _normalize_parsed_url(parsed) -> str:
    host = (parsed.hostname or "").lower().rstrip(".")
    return urlunparse(("https", host, parsed.path or "/", "", parsed.query, ""))


def _is_specific_youtube_url(parsed) -> bool:
    host = (parsed.hostname or "").lower()
    parts = [part for part in parsed.path.split("/") if part]
    query = parse_qs(parsed.query)

    if host == "youtu.be":
        return bool(parts and parts[0])
    if parts[:1] == ["watch"]:
        return bool(query.get("v"))
    if parts[:1] == ["playlist"]:
        return bool(query.get("list"))
    if parts[:1] in (["shorts"], ["embed"], ["live"]):
        return len(parts) >= 2 and bool(parts[1])
    return False


def _is_specific_public_item(platform: str, host: str, parsed) -> bool:
    parts = [part for part in parsed.path.split("/") if part]
    query = parse_qs(parsed.query)

    if platform == "instagram":
        return len(parts) >= 2 and parts[0].lower() in {"p", "reel", "reels", "tv"}
    if platform == "tiktok":
        if host.startswith("vm.") or host.startswith("vt."):
            return bool(parts)
        lowered = [part.lower() for part in parts]
        return "video" in lowered or "photo" in lowered or (len(parts) >= 2 and lowered[0] == "t")
    if platform == "facebook":
        if host == "fb.watch" or host.endswith(".fb.watch"):
            return bool(parts)
        lowered = [part.lower() for part in parts]
        if query.get("v"):
            return True
        if lowered[:1] in (["watch"], ["reel"], ["reels"]):
            return len(parts) >= 2
        if "videos" in lowered:
            index = lowered.index("videos")
            return index + 1 < len(parts)
        return False
    if platform == "x":
        lowered = [part.lower() for part in parts]
        return "status" in lowered and lowered.index("status") + 1 < len(parts)
    if platform == "pinterest":
        if host == "pin.it" or host.endswith(".pin.it"):
            return bool(parts)
        return len(parts) >= 2 and parts[0].lower() == "pin"
    if platform == "linkedin":
        path = parsed.path.lower()
        return path.startswith("/posts/") or path.startswith("/feed/update/") or path.startswith("/video/")
    if platform == "dailymotion":
        if host == "dai.ly" or host.endswith(".dai.ly"):
            return bool(parts)
        return len(parts) >= 2 and parts[0].lower() in {"video", "embed"}
    if platform == "twitch":
        lowered = [part.lower() for part in parts]
        return host.startswith("clips.") or (parts and lowered[0] == "videos") or "clip" in lowered
    if platform == "bluesky":
        lowered = [part.lower() for part in parts]
        return len(parts) >= 4 and lowered[0] == "profile" and "post" in lowered
    if platform == "loom":
        return len(parts) >= 2 and parts[0].lower() in {"share", "embed"}
    if platform == "apple_podcasts":
        return bool(parts) and bool(query.get("i"))
    return False
