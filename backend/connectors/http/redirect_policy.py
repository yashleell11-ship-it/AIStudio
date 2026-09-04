"""Per-hop validation of connector HTTP redirects (SSRF guard).

The scrape clients used to follow redirects blindly (``follow_redirects=True``
/ ``allow_redirects=True``), so any allowlisted upstream — a hostile site
operator, a compromised site, or whoever re-registers a lapsed domain — could
302 the backend at an arbitrary target, including plain-HTTP services on the
private docker network this container shares with other workloads. Only the
image/cover proxy path validated its URLs (``services.outbound_security``);
the HTML/JSON scrape path had no check at all.

Every redirect hop is now validated *before* it is followed:

* the target must be ``https`` (no downgrade to plain HTTP);
* the target host must be the client's own site (its base host, ``www.``
  stripped) or a subdomain of it; and
* the target host must resolve to public addresses only.

A hop that fails any check aborts the request with ``ConnectorHttpError`` —
fail closed: a source that redirects off its own domain looks exactly like a
source that got parked or compromised, and this fleet churns constantly (the
repo already ships parking-page detection because that has happened).

This module is deliberately free of non-stdlib imports at module scope so both
the httpx client and the curl_cffi clients can share it without cycles.
"""

from __future__ import annotations

import ipaddress
import socket
import threading
import time
from collections import OrderedDict
from typing import Any
from urllib.parse import urljoin, urlparse

#: Redirect statuses browsers (and httpx/libcurl) follow.
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

#: Hop ceiling for the manual redirect loop used by the curl_cffi clients.
DEFAULT_MAX_REDIRECT_HOPS = 5


def host_matches_allowlist(hostname: str, allowed_hosts: frozenset[str]) -> bool:
    """True when ``hostname`` equals an allowlisted domain or is a subdomain of
    one. The dot boundary matters: ``notexample.com`` must never match an
    allowlist entry of ``example.com``."""
    hostname = hostname.lower()
    return any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in allowed_hosts
    )


#: How long a hostname's resolution verdict is reused. Deliberately short —
#: see ``is_public_address`` for why this is safe, and why it is not free.
PUBLIC_ADDRESS_TTL_SECONDS = 60.0
#: Ceiling on remembered hostnames. The allowlist already bounds which hosts
#: can reach the resolver at all; this is belt and braces against a source
#: that serves images from thousands of per-object subdomains.
_PUBLIC_ADDRESS_MAX_HOSTS = 512

_public_address_cache: "OrderedDict[str, tuple[float, bool]]" = OrderedDict()
_public_address_lock = threading.Lock()


def _resolves_public(hostname: str) -> bool:
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


def is_public_address(hostname: str) -> bool:
    """Resolve ``hostname`` and confirm every address it maps to is public.

    The verdict is cached for ``PUBLIC_ADDRESS_TTL_SECONDS`` because this sits
    on the image proxy's per-image path: a chapter is 20-100 images off ONE CDN
    hostname, and each one was paying a blocking ``getaddrinfo``. Measured from
    the production container, that is ~1.2 ms median — but 117 ms at p95 and
    163 ms at worst, and it is serial with the fetch, so a long chapter could
    spend seconds resolving a name it had just resolved.

    Why a cache does not weaken the guard:

    * ``host_matches_allowlist`` runs FIRST and is untouched. Only hostnames
      under a connector's own declared CDN domains ever reach this function, so
      the cache can never hold a host the allowlist would have rejected.
    * The check is already time-of-check/time-of-use: the address validated
      here is not the one httpx or libcurl later connects with — they resolve
      again. A rebinding window therefore already exists; the TTL widens it
      from milliseconds to a minute rather than creating it, and exploiting it
      still requires controlling DNS for a domain the connector allowlists,
      which is game over regardless.
    * Both verdicts are cached for the same TTL. Caching the *failure* keeps
      the guard fail-closed and cheap, and a minute is short enough that a CDN
      recovering from a resolver blip is not stuck.
    """
    now = time.monotonic()
    with _public_address_lock:
        entry = _public_address_cache.get(hostname)
        if entry is not None and entry[0] > now:
            _public_address_cache.move_to_end(hostname)
            return entry[1]

    verdict = _resolves_public(hostname)

    with _public_address_lock:
        _public_address_cache[hostname] = (
            now + PUBLIC_ADDRESS_TTL_SECONDS,
            verdict,
        )
        _public_address_cache.move_to_end(hostname)
        while len(_public_address_cache) > _PUBLIC_ADDRESS_MAX_HOSTS:
            _public_address_cache.popitem(last=False)
    return verdict


def reset_public_address_cache() -> None:
    """Forget every remembered verdict. For tests."""
    with _public_address_lock:
        _public_address_cache.clear()


def allowed_redirect_hosts(
    base_url: str, extra_hosts: frozenset[str] | set[str] | None = None
) -> frozenset[str]:
    """The redirect allowlist a scrape client derives from its own base URL.

    The site's host with any leading ``www.`` stripped, so a redirect between
    ``www.example.com``, ``example.com`` and ``cdn.example.com`` (all routine
    for these sites) stays followable via the subdomain match, while anything
    off-domain is not.

    ``extra_hosts`` declares additional domains a *specific* source legitimately
    spans, for the case where one operator splits a source across two names —
    BaoZiMH browses on baozimh.com but every chapter 302s to its twmanga.com
    reader, so a base-host-only allowlist makes the source unreadable. Keep
    these explicit and per-connector: the default stays fail-closed, and a
    parked or hijacked domain still cannot redirect the backend anywhere new.
    """
    host = (urlparse(base_url).hostname or "").strip().lower()
    hosts = {host} if host else set()
    for extra in extra_hosts or ():
        extra = extra.strip().lower()
        if extra.startswith("www."):
            extra = extra[4:]
        if extra:
            hosts.add(extra)
    if host.startswith("www."):
        hosts.discard(host)
        hosts.add(host[4:])
    return frozenset(hosts)


def redirect_rejection_reason(
    target_url: str, allowed_hosts: frozenset[str]
) -> str | None:
    """Why ``target_url`` must not be followed, or ``None`` when it may be."""
    parsed = urlparse(target_url)
    if parsed.scheme != "https":
        return f"non-https redirect target ({parsed.scheme or 'no scheme'})"
    hostname = parsed.hostname
    if not hostname:
        return "redirect target has no hostname"
    if not allowed_hosts or not host_matches_allowlist(hostname, allowed_hosts):
        return f"redirect target host '{hostname}' is off this source's domain"
    if not is_public_address(hostname):
        return (
            f"redirect target host '{hostname}' does not resolve to a public address"
        )
    return None


def send_with_redirect_validation(
    session: Any,
    method: str,
    url: str,
    *,
    allowed_hosts: frozenset[str],
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
    params: Any = None,
    data: Any = None,
    max_hops: int = DEFAULT_MAX_REDIRECT_HOPS,
) -> Any:
    """Issue ``method url`` on a curl_cffi-style session, following redirects
    manually with every hop validated first.

    libcurl offers no per-hop callback, so ``allow_redirects`` is forced off
    and the chain is walked here. ``params``/``data`` apply to the first
    request only — a redirect ``Location`` carries its own query string — and
    a 303 (or a 301/302 after a POST) is re-issued as a GET, matching the
    browser behaviour these clients impersonate.

    Raises ``ConnectorHttpError`` on a blocked hop or when ``max_hops`` is
    exceeded.
    """
    # Local import: client.py imports this module at its top, so importing the
    # error class lazily avoids the cycle.
    from connectors.http.client import ConnectorHttpError

    current_method = method.upper()
    current_url = url
    current_params = params
    current_data = data
    for _ in range(max_hops + 1):
        response = session.request(
            current_method,
            current_url,
            params=current_params,
            data=current_data,
            headers=headers,
            timeout=timeout,
            allow_redirects=False,
        )
        location = (
            response.headers.get("location")
            if response.status_code in REDIRECT_STATUSES
            else None
        )
        if not location:
            return response
        target = urljoin(str(getattr(response, "url", "") or current_url), location)
        reason = redirect_rejection_reason(target, allowed_hosts)
        if reason:
            raise ConnectorHttpError(
                f"Redirect blocked ({reason}).", status_code=502
            )
        if response.status_code == 303 or (
            current_method == "POST" and response.status_code in (301, 302)
        ):
            current_method = "GET"
            current_data = None
        current_url = target
        current_params = None
    raise ConnectorHttpError("Too many redirects.", status_code=502)
