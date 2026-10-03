from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.parse import urljoin, urlparse, urlunparse


class FetchSafetyError(ValueError):
    """Raised when a backend fetch target fails the network safety policy."""


Resolver = Callable[[str, int], Iterable[tuple]]


@dataclass(frozen=True)
class ValidatedFetchTarget:
    url: str
    host: str
    port: int
    resolved_ips: frozenset[str]


@dataclass(frozen=True)
class FetchPolicy:
    max_redirects: int = 5


def validate_fetch_target(
    value: str,
    *,
    resolver: Resolver = socket.getaddrinfo,
) -> ValidatedFetchTarget:
    """Validate and resolve one HTTP(S) target before a backend request.

    The returned address set is a preflight receipt, not permission to trust a
    later connection. Call ``validate_connected_peer`` with the actual peer IP
    after connecting so DNS rebinding/address drift fails closed.
    """

    parsed = urlparse((value or "").strip())
    if parsed.scheme not in {"http", "https"}:
        raise FetchSafetyError("Only http and https fetch targets are allowed.")
    if parsed.username is not None or parsed.password is not None:
        raise FetchSafetyError("Embedded URL credentials are not allowed.")

    try:
        explicit_port = parsed.port
    except ValueError as exc:
        raise FetchSafetyError("The fetch target contains an invalid port.") from exc

    expected_port = 443 if parsed.scheme == "https" else 80
    port = explicit_port or expected_port
    if port != expected_port:
        raise FetchSafetyError("Only the standard port for the URL scheme is allowed.")

    host = (parsed.hostname or "").casefold().rstrip(".")
    if not host:
        raise FetchSafetyError("The fetch target must contain a hostname.")

    addresses = _resolve_public_addresses(host, port, resolver)
    normalized = urlunparse((parsed.scheme, host, parsed.path or "/", "", parsed.query, ""))
    return ValidatedFetchTarget(
        url=normalized,
        host=host,
        port=port,
        resolved_ips=frozenset(addresses),
    )


def validate_redirect_target(
    current_url: str,
    location: str,
    *,
    redirect_count: int,
    policy: FetchPolicy = FetchPolicy(),
    resolver: Resolver = socket.getaddrinfo,
) -> ValidatedFetchTarget:
    """Resolve and revalidate every redirect target before following it."""

    if redirect_count < 0:
        raise FetchSafetyError("Redirect count cannot be negative.")
    if redirect_count >= policy.max_redirects:
        raise FetchSafetyError("Redirect limit exceeded.")
    if not (location or "").strip():
        raise FetchSafetyError("Redirect location is empty.")

    target = urljoin(current_url, location)
    return validate_fetch_target(target, resolver=resolver)


def validate_connected_peer(peer_ip: str, target: ValidatedFetchTarget) -> str:
    """Bind a connection to the preflight DNS result and reject address drift."""

    try:
        address = ipaddress.ip_address((peer_ip or "").strip())
    except ValueError as exc:
        raise FetchSafetyError("Connected peer is not a valid IP address.") from exc

    canonical = address.compressed
    _require_global_address(address)
    if canonical not in target.resolved_ips:
        raise FetchSafetyError("Connected peer does not match the validated DNS result.")
    return canonical


def _resolve_public_addresses(host: str, port: int, resolver: Resolver) -> set[str]:
    # IP literals bypass DNS but are held to the same global-address policy.
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        _require_global_address(literal)
        return {literal.compressed}

    try:
        records = list(resolver(host, port))
    except (OSError, socket.gaierror) as exc:
        raise FetchSafetyError("The fetch target could not be resolved.") from exc

    addresses: set[str] = set()
    for record in records:
        try:
            sockaddr = record[4]
            raw_ip = sockaddr[0]
            address = ipaddress.ip_address(raw_ip)
        except (IndexError, TypeError, ValueError) as exc:
            raise FetchSafetyError("Resolver returned an invalid address record.") from exc
        _require_global_address(address)
        addresses.add(address.compressed)

    if not addresses:
        raise FetchSafetyError("The fetch target resolved to no usable addresses.")
    return addresses


def _require_global_address(address: ipaddress._BaseAddress) -> None:
    # ``is_global`` fails closed for loopback, private, link-local, multicast,
    # unspecified, reserved and documentation-only ranges in Python's stdlib.
    if not address.is_global:
        raise FetchSafetyError("The fetch target resolves to a non-public network address.")
