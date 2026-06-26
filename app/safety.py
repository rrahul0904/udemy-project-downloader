from __future__ import annotations

from urllib.parse import urlparse, urlunparse


class UrlValidationError(ValueError):
    """Raised when a submitted URL is outside the supported Udemy scope."""


def normalize_udemy_url(value: str) -> str:
    url = (value or "").strip()
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        raise UrlValidationError("Use a full http or https Udemy course URL.")

    host = (parsed.hostname or "").lower()
    if not (host == "udemy.com" or host.endswith(".udemy.com")):
        raise UrlValidationError("Only udemy.com and *.udemy.com course URLs are supported.")

    if not parsed.path or parsed.path == "/":
        raise UrlValidationError("Paste a specific Udemy course URL.")

    netloc = parsed.netloc.lower()
    return urlunparse(("https", netloc, parsed.path, "", parsed.query, ""))


def slug_from_url(value: str) -> str:
    parsed = urlparse(value)
    parts = [part for part in parsed.path.split("/") if part]
    candidate = parts[-1] if parts else parsed.hostname or "course"
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in candidate)
    safe = "-".join(part for part in safe.split("-") if part)
    return safe[:80] or "course"

