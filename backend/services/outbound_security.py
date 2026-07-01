"""Shared outbound URL validation for connector image fetches."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from connectors.base import SourceConnector
from core.errors import AppError


def host_matches_allowlist(hostname: str, allowed_hosts: frozenset[str]) -> bool:
    return any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in allowed_hosts
    )


def is_public_address(hostname: str) -> bool:
    """Resolve ``hostname`` and confirm every address it maps to is public."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = info[4][0]
        address = ipaddress.ip_address(ip)
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
        ):
            return False
    return True


def validate_outbound_url(url: str, connector: SourceConnector) -> str:
    """Validate ``url`` against the connector's approved domain allowlist.

    Returns the validated hostname. Raises ``AppError`` (code ``ssrf_blocked``)
    if the URL is not HTTPS, has no host, the host is not on the connector's
    ``allowed_image_hosts``, or the host resolves to a non-public address.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise AppError(
            "Only HTTPS URLs may be fetched.",
            code="ssrf_blocked",
            status_code=400,
            details={"url": url},
        )

    hostname = parsed.hostname
    if not hostname:
        raise AppError(
            "Remote URL has no hostname.",
            code="ssrf_blocked",
            status_code=400,
            details={"url": url},
        )

    allowed_hosts = connector.allowed_image_hosts
    if not allowed_hosts or not host_matches_allowlist(hostname, allowed_hosts):
        raise AppError(
            "Remote host is not an approved domain for this source.",
            code="ssrf_blocked",
            status_code=400,
            details={"host": hostname, "source": connector.source_type},
        )

    if not is_public_address(hostname):
        raise AppError(
            "Remote host does not resolve to a public address.",
            code="ssrf_blocked",
            status_code=400,
            details={"host": hostname},
        )

    return hostname
