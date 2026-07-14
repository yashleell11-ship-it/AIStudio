"""HTTP client for DDoS-Guard-protected HTML sources."""

from __future__ import annotations

import json
import secrets
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


def is_ddos_guard_challenge(html: str) -> bool:
    """Return True when HTML is a DDoS-Guard interstitial rather than site content."""
    lowered = html.lower()
    if "post-loop" in lowered or "entry-content" in lowered:
        return False
    return "ddos-guard" in lowered and "checking your browser" in lowered


class DdgSyncHttpClient:
    """Sync client using curl_cffi browser TLS impersonation and DDoS-Guard bypass."""

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
        domain = self._base_url.removeprefix("https://").removeprefix("http://").split("/")[0]
        # gallery-dl/kemono pattern: any __ddg2_ value satisfies the JS check screen.
        self._session.cookies.set(
            "__ddg2_",
            secrets.token_hex(8),
            domain=f".{domain.lstrip('.')}",
        )

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
                if is_ddos_guard_challenge(html):
                    raise ConnectorHttpError(
                        "DDoS-Guard challenge blocked the request.",
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

    def post_text(
        self,
        path: str,
        *,
        data: dict[str, str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> str:
        """POST form data and return the response text."""
        url = self._resolve_url(path)
        last_error: Exception | None = None
        headers = dict(self._headers)
        headers.setdefault("Accept", "application/json, text/javascript, */*; q=0.01")
        headers.setdefault("X-Requested-With", "XMLHttpRequest")
        if extra_headers:
            headers.update(extra_headers)

        for attempt in range(self._max_retries):
            self._rate_limit()
            try:
                response = self._session.post(
                    url,
                    data=data or {},
                    headers=headers,
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

    def post_json(
        self,
        path: str,
        *,
        data: dict[str, str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        """POST form data and return the decoded JSON body."""
        url = self._resolve_url(path)
        last_error: Exception | None = None
        headers = dict(self._headers)
        headers.setdefault("Accept", "application/json, text/javascript, */*; q=0.01")
        headers.setdefault("X-Requested-With", "XMLHttpRequest")
        if extra_headers:
            headers.update(extra_headers)

        for attempt in range(self._max_retries):
            self._rate_limit()
            try:
                response = self._session.post(
                    url,
                    data=data or {},
                    headers=headers,
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
                return json.loads(response.text)
            except (ConnectorHttpError, OSError, json.JSONDecodeError) as exc:
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

    def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        """GET JSON from an API path and return the decoded body."""
        url = self._resolve_url(path)
        last_error: Exception | None = None
        headers = dict(self._headers)
        headers["Accept"] = "application/json, text/plain, */*"
        if extra_headers:
            headers.update(extra_headers)

        for attempt in range(self._max_retries):
            self._rate_limit()
            try:
                response = self._session.get(
                    url,
                    params=_serialize_params(params),
                    headers=headers,
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
                return json.loads(response.text)
            except (ConnectorHttpError, OSError, json.JSONDecodeError) as exc:
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

    def get_bytes(
        self,
        url: str,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[str, bytes]:
        """GET a binary resource (e.g. CDN image) and return content-type + body."""
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
