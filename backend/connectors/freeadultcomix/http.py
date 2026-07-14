"""curl_cffi client with DoH DNS for freeadultcomix.com.

The apex domain is frequently rewritten by ISP RPZ filters
(``restricted.rpz.airtelspam.com``) to a dead IP. Cloudflare DoH returns the
real CF anycast addresses; we pin them via ``CURLOPT_RESOLVE`` so listing and
image fetches succeed from poisoned resolvers.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urljoin, urlparse

from curl_cffi import CurlOpt
from curl_cffi.requests import Session

from connectors.http.client import RETRYABLE_STATUS, ConnectorHttpError

logger = logging.getLogger(__name__)

DOH_URL = "https://cloudflare-dns.com/dns-query"
DEFAULT_HOSTS = ("freeadultcomix.com", "www.freeadultcomix.com")


def _serialize_params(params: dict[str, Any] | None) -> dict[str, str] | None:
    if not params:
        return None
    serialized: dict[str, str] = {}
    for key, value in params.items():
        if value is not None:
            serialized[key] = str(value)
    return serialized or None


def resolve_host_ips(hostname: str, *, timeout: float = 8.0) -> list[str]:
    """Resolve A records via Cloudflare DNS-over-HTTPS."""
    url = f"{DOH_URL}?name={hostname}&type=A"
    request = urllib.request.Request(url, headers={"Accept": "application/dns-json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    ips: list[str] = []
    for answer in payload.get("Answer") or []:
        if answer.get("type") == 1 and isinstance(answer.get("data"), str):
            ips.append(answer["data"])
    return ips


def build_resolve_entries(hosts: tuple[str, ...] = DEFAULT_HOSTS) -> list[str]:
    """Build libcurl ``RESOLVE`` entries ``host:443:ip`` for each host."""
    entries: list[str] = []
    seen: set[str] = set()
    for host in hosts:
        try:
            ips = resolve_host_ips(host)
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            logger.warning("DoH lookup failed for %s: %s", host, exc)
            continue
        for ip in ips:
            entry = f"{host}:443:{ip}"
            if entry not in seen:
                seen.add(entry)
                entries.append(entry)
    return entries


class FacSyncHttpClient:
    """Browser-TLS client pinned to DoH-resolved Cloudflare IPs."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        min_interval: float = 0.35,
        headers: dict[str, str] | None = None,
        impersonate: str = "chrome131",
        resolve_entries: list[str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._min_interval = min_interval
        self._last_request = 0.0
        request_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"{self._base_url}/",
        }
        if headers:
            request_headers.update(headers)
        self._headers = request_headers
        self._impersonate = impersonate
        self._resolve_entries = resolve_entries if resolve_entries is not None else build_resolve_entries()
        self._session = self._make_session()

    def _make_session(self) -> Session:
        curl_options: dict[Any, Any] = {}
        if self._resolve_entries:
            curl_options[CurlOpt.RESOLVE] = list(self._resolve_entries)
        if curl_options:
            return Session(impersonate=self._impersonate, curl_options=curl_options)
        return Session(impersonate=self._impersonate)

    def refresh_dns(self) -> None:
        """Re-resolve hosts and rebuild the session (call after connect failures)."""
        self._resolve_entries = build_resolve_entries()
        try:
            self._session.close()
        except Exception:
            pass
        self._session = self._make_session()

    def _rate_limit(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.monotonic()

    def _resolve_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return urljoin(f"{self._base_url}/", path.lstrip("/"))

    def get_text(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> str:
        url = self._resolve_url(path)
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            self._rate_limit()
            try:
                response = self._session.get(
                    url,
                    params=_serialize_params(params),
                    headers=self._headers,
                    timeout=self._timeout,
                    allow_redirects=True,
                )
                if response.status_code in RETRYABLE_STATUS:
                    raise ConnectorHttpError(
                        f"Retryable HTTP {response.status_code}",
                        status_code=response.status_code,
                    )
                if response.status_code >= 400:
                    raise ConnectorHttpError(
                        f"Client error '{response.status_code} {response.reason}' for url '{url}'",
                        status_code=response.status_code,
                    )
                return response.text
            except (ConnectorHttpError, OSError) as exc:
                last_error = exc
                if attempt == 0:
                    self.refresh_dns()
                if attempt + 1 >= self._max_retries:
                    break
                time.sleep(0.5 * (2**attempt))

        message = str(last_error) if last_error else "Unknown HTTP error"
        status_code = (
            last_error.status_code
            if isinstance(last_error, ConnectorHttpError)
            else None
        )
        raise ConnectorHttpError(message, status_code=status_code) from last_error

    def get_bytes(
        self,
        url: str,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[str, bytes]:
        if not url.startswith("http://") and not url.startswith("https://"):
            url = self._resolve_url(url)
        last_error: Exception | None = None
        headers = dict(self._headers)
        headers["Accept"] = "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"
        if extra_headers:
            headers.update(extra_headers)

        for attempt in range(self._max_retries):
            self._rate_limit()
            try:
                response = self._session.get(
                    url,
                    headers=headers,
                    timeout=self._timeout,
                    allow_redirects=False,
                )
                if response.status_code in RETRYABLE_STATUS:
                    raise ConnectorHttpError(
                        f"Retryable HTTP {response.status_code}",
                        status_code=response.status_code,
                    )
                if response.status_code >= 400:
                    raise ConnectorHttpError(
                        f"Client error '{response.status_code} {response.reason}' for url '{url}'",
                        status_code=response.status_code,
                    )
                media_type = response.headers.get("content-type", "image/jpeg").split(";")[0]
                return media_type, response.content
            except (ConnectorHttpError, OSError) as exc:
                last_error = exc
                if attempt == 0 and urlparse(url).hostname in DEFAULT_HOSTS:
                    self.refresh_dns()
                if attempt + 1 >= self._max_retries:
                    break
                time.sleep(0.5 * (2**attempt))

        message = str(last_error) if last_error else "Unknown HTTP error"
        status_code = (
            last_error.status_code
            if isinstance(last_error, ConnectorHttpError)
            else None
        )
        raise ConnectorHttpError(message, status_code=status_code) from last_error

    def close(self) -> None:
        self._session.close()
