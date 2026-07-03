"""HTTP client for Cloudflare-protected HTML sources."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urljoin

from curl_cffi.requests import Session

from connectors.http.client import ConnectorHttpError, RETRYABLE_STATUS


def _serialize_params(params: dict[str, Any] | None) -> dict[str, str] | None:
    if not params:
        return None
    serialized: dict[str, str] = {}
    for key, value in params.items():
        if value is not None:
            serialized[key] = str(value)
    return serialized or None


def is_cloudflare_challenge(html: str) -> bool:
    """Return True when HTML is a Cloudflare interstitial rather than site content."""
    lowered = html.lower()
    if "page-item-detail" in lowered or "wp-manga" in lowered:
        return False
    return (
        "just a moment" in lowered
        or "enable javascript and cookies to continue" in lowered
    )


class CfSyncHttpClient:
    """Sync client using curl_cffi browser TLS impersonation."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        min_interval: float = 0.21,
        headers: dict[str, str] | None = None,
        impersonate: str = "chrome131",
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
        self._session = Session(impersonate=impersonate)

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
                html = response.text
                if is_cloudflare_challenge(html):
                    raise ConnectorHttpError(
                        "Cloudflare challenge blocked the request.",
                        status_code=403,
                    )
                return html
            except (ConnectorHttpError, OSError) as exc:
                last_error = exc
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
