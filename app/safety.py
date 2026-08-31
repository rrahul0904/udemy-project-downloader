from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse, urlunparse


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
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        raise UrlValidationError("Use a full http or https Udemy or YouTube URL.")
    if parsed.username is not None or parsed.password is not None:
        raise UrlValidationError("Embedded URL credentials are not allowed.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise UrlValidationError("The source URL contains an invalid port.") from exc
    if port not in {None, 80, 443}:
        raise UrlValidationError("Only standard web ports are allowed for source URLs.")

    host = (parsed.hostname or "").lower()
    if _is_udemy_host(host):
        if not parsed.path or parsed.path == "/":
            raise UrlValidationError("Paste a specific Udemy course URL.")
        return NormalizedUrl(_normalize_parsed_url(parsed), "udemy")

    if host in YOUTUBE_HOSTS:
        if not _is_specific_youtube_url(parsed):
            raise UrlValidationError("Paste a specific YouTube video, Shorts, live, or playlist URL.")
        return NormalizedUrl(_normalize_parsed_url(parsed), "youtube")

    raise UrlValidationError("Only Udemy course URLs and YouTube video or playlist URLs are supported.")


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
        candidate = parts[-1] if parts else parsed.hostname or "course"

    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in candidate)
    safe = "-".join(part for part in safe.split("-") if part)
    return safe[:80] or "course"


def _is_udemy_host(host: str) -> bool:
    return host == "udemy.com" or host.endswith(".udemy.com")


def _normalize_parsed_url(parsed) -> str:
    host = (parsed.hostname or "").lower()
    return urlunparse(("https", host, parsed.path, "", parsed.query, ""))


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
