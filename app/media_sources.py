from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from urllib.parse import urlparse


class MediaSourceError(ValueError):
    """Raised when a URL cannot be safely classified as a media source."""


class ImplementationState(str, Enum):
    EXISTING = "existing"
    GENERIC_YTDLP = "generic_yt_dlp"
    RESEARCH_ONLY = "research_only"


class PolicyMode(str, Enum):
    AUTHORIZED_SESSION = "authorized_session"
    PUBLIC_OR_AUTHORIZED = "public_or_authorized"


@dataclass(frozen=True)
class SourceCapabilities:
    video: bool = False
    audio: bool = False
    photo: bool = False
    carousel: bool = False
    gif: bool = False


@dataclass(frozen=True)
class SourceSpec:
    key: str
    display_name: str
    hosts: tuple[str, ...]
    capabilities: SourceCapabilities
    policy_mode: PolicyMode
    implementation_state: ImplementationState = ImplementationState.RESEARCH_ONLY

    @property
    def archive_enabled(self) -> bool:
        return self.implementation_state in {
            ImplementationState.EXISTING,
            ImplementationState.GENERIC_YTDLP,
        }


@dataclass(frozen=True)
class DetectedSource:
    source: SourceSpec
    canonical_host: str


# RE-382 source registry.
# EXISTING = repository-specific path already present before RE-382.
# GENERIC_YTDLP = source has a current yt-dlp extractor and is enabled only for
# public/authorized item URLs through the same bounded job runtime.
# RESEARCH_ONLY = donor capability is known but no adapter is enabled yet.
_SOURCE_SPECS = (
    SourceSpec(
        "instagram",
        "Instagram",
        ("instagram.com",),
        SourceCapabilities(video=True, audio=True, photo=True, carousel=True),
        PolicyMode.PUBLIC_OR_AUTHORIZED,
        ImplementationState.GENERIC_YTDLP,
    ),
    SourceSpec(
        "tiktok",
        "TikTok",
        ("tiktok.com",),
        SourceCapabilities(video=True, audio=True, photo=True, carousel=True),
        PolicyMode.PUBLIC_OR_AUTHORIZED,
        ImplementationState.GENERIC_YTDLP,
    ),
    SourceSpec(
        "youtube",
        "YouTube",
        ("youtube.com", "youtu.be", "youtube-nocookie.com"),
        SourceCapabilities(video=True, audio=True),
        PolicyMode.PUBLIC_OR_AUTHORIZED,
        ImplementationState.EXISTING,
    ),
    SourceSpec(
        "facebook",
        "Facebook",
        ("facebook.com", "fb.watch"),
        SourceCapabilities(video=True, audio=True),
        PolicyMode.PUBLIC_OR_AUTHORIZED,
        ImplementationState.GENERIC_YTDLP,
    ),
    SourceSpec(
        "x",
        "X",
        ("x.com", "twitter.com"),
        SourceCapabilities(video=True, audio=True, photo=True, gif=True),
        PolicyMode.PUBLIC_OR_AUTHORIZED,
        ImplementationState.GENERIC_YTDLP,
    ),
    SourceSpec(
        "pinterest",
        "Pinterest",
        ("pinterest.com", "pin.it"),
        SourceCapabilities(video=True, audio=True, photo=True),
        PolicyMode.PUBLIC_OR_AUTHORIZED,
        ImplementationState.GENERIC_YTDLP,
    ),
    SourceSpec(
        "threads",
        "Threads",
        ("threads.net",),
        SourceCapabilities(video=True, photo=True),
        PolicyMode.PUBLIC_OR_AUTHORIZED,
    ),
    SourceSpec(
        "snapchat",
        "Snapchat",
        ("snapchat.com",),
        SourceCapabilities(video=True, audio=True),
        PolicyMode.PUBLIC_OR_AUTHORIZED,
    ),
    SourceSpec(
        "linkedin",
        "LinkedIn",
        ("linkedin.com",),
        SourceCapabilities(video=True, audio=True),
        PolicyMode.PUBLIC_OR_AUTHORIZED,
        ImplementationState.GENERIC_YTDLP,
    ),
    SourceSpec(
        "dailymotion",
        "Dailymotion",
        ("dailymotion.com", "dai.ly"),
        SourceCapabilities(video=True, audio=True),
        PolicyMode.PUBLIC_OR_AUTHORIZED,
        ImplementationState.GENERIC_YTDLP,
    ),
    SourceSpec(
        "twitch",
        "Twitch",
        ("twitch.tv",),
        SourceCapabilities(video=True, audio=True),
        PolicyMode.PUBLIC_OR_AUTHORIZED,
        ImplementationState.GENERIC_YTDLP,
    ),
    SourceSpec(
        "bluesky",
        "Bluesky",
        ("bsky.app",),
        SourceCapabilities(video=True, audio=True),
        PolicyMode.PUBLIC_OR_AUTHORIZED,
        ImplementationState.GENERIC_YTDLP,
    ),
    SourceSpec(
        "sharechat",
        "ShareChat",
        ("sharechat.com",),
        SourceCapabilities(video=True, photo=True),
        PolicyMode.PUBLIC_OR_AUTHORIZED,
    ),
    SourceSpec(
        "moj",
        "Moj",
        ("mojapp.in",),
        SourceCapabilities(video=True),
        PolicyMode.PUBLIC_OR_AUTHORIZED,
    ),
    SourceSpec(
        "loom",
        "Loom",
        ("loom.com",),
        SourceCapabilities(video=True, audio=True),
        PolicyMode.PUBLIC_OR_AUTHORIZED,
        ImplementationState.GENERIC_YTDLP,
    ),
    SourceSpec(
        "giphy",
        "Giphy",
        ("giphy.com",),
        SourceCapabilities(video=True, gif=True),
        PolicyMode.PUBLIC_OR_AUTHORIZED,
    ),
    SourceSpec(
        "tenor",
        "Tenor",
        ("tenor.com",),
        SourceCapabilities(video=True, gif=True),
        PolicyMode.PUBLIC_OR_AUTHORIZED,
    ),
    SourceSpec(
        "apple_podcasts",
        "Apple Podcasts",
        ("podcasts.apple.com",),
        SourceCapabilities(audio=True),
        PolicyMode.PUBLIC_OR_AUTHORIZED,
        ImplementationState.GENERIC_YTDLP,
    ),
    SourceSpec(
        "udemy",
        "Udemy",
        ("udemy.com",),
        SourceCapabilities(video=True, audio=True),
        PolicyMode.AUTHORIZED_SESSION,
        ImplementationState.EXISTING,
    ),
)

SOURCE_REGISTRY = MappingProxyType({spec.key: spec for spec in _SOURCE_SPECS})


def detect_media_source(value: str) -> DetectedSource:
    """Classify a submitted URL without performing any network request."""

    parsed = urlparse((value or "").strip())
    if parsed.scheme not in {"http", "https"}:
        raise MediaSourceError("Use a full http or https URL.")
    if parsed.username is not None or parsed.password is not None:
        raise MediaSourceError("Embedded URL credentials are not allowed.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise MediaSourceError("The source URL contains an invalid port.") from exc
    if port not in {None, 80, 443}:
        raise MediaSourceError("Only standard web ports are allowed for source URLs.")

    host = (parsed.hostname or "").casefold().rstrip(".")
    if not host:
        raise MediaSourceError("The source URL must contain a hostname.")

    for spec in _SOURCE_SPECS:
        matched = _match_host(host, spec.hosts)
        if matched is not None:
            return DetectedSource(source=spec, canonical_host=matched)

    raise MediaSourceError("Unsupported or unknown media source.")


def _match_host(host: str, allowed_hosts: tuple[str, ...]) -> str | None:
    for allowed in allowed_hosts:
        candidate = allowed.casefold().rstrip(".")
        if host == candidate or host.endswith(f".{candidate}"):
            return candidate
    return None
