"""Shared outbound URL validation for connector image fetches.

The pure host/address checks live in ``connectors.http.redirect_policy`` so
the scrape clients' per-hop redirect validation and this image-proxy
validation share one implementation. They are re-exported here because this
module is the historical import site (tests patch
``services.outbound_security.is_public_address``).
"""

from __future__ import annotations

from urllib.parse import urlparse

from connectors.base import SourceConnector
from connectors.http.redirect_policy import (  # noqa: F401 - re-exported
    host_matches_allowlist,
    is_public_address,
)
from core.errors import AppError


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
