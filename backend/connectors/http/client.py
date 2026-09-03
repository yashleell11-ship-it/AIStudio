"""Shared HTTP utilities for source connectors."""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import httpx

from connectors.http.redirect_policy import (
    allowed_redirect_hosts,
    redirect_rejection_reason,
)

DEFAULT_USER_AGENT = "ManhwaManiacs/0.1 (local manga reader; +https://github.com/manhwamaniacs)"
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def _serialize_params(params: dict[str, Any] | None) -> list[tuple[str, str]] | None:
    if not params:
        return None
    items: list[tuple[str, str]] = []
    for key, value in params.items():
        if isinstance(value, list):
            for item in value:
                items.append((key, str(item)))
        elif value is not None:
            items.append((key, str(value)))
    return items


class ConnectorHttpError(Exception):
    """Raised when a connector HTTP request fails after retries."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SyncConnectorHttpClient:
    """Sync HTTP client with retries for connector implementations."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        min_interval: float = 0.21,
        user_agent: str = DEFAULT_USER_AGENT,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._min_interval = min_interval
        self._last_request = 0.0
        self._rate_lock = threading.Lock()
        request_headers = {
            "User-Agent": user_agent,
            "Accept": "application/json",
        }
        if headers:
            request_headers.update(headers)
        self._redirect_hosts = allowed_redirect_hosts(self._base_url)
        # follow_redirects stays on, but every hop is validated by the
        # response event hook below BEFORE httpx issues the follow-up request
        # (httpx runs response hooks inside its redirect loop) — an upstream
        # 302 must never point this backend at an off-domain or internal
        # target (SSRF; see connectors/http/redirect_policy.py).
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=self._timeout,
            headers=request_headers,
            follow_redirects=True,
            event_hooks={"response": [self._guard_redirect]},
        )

    def _guard_redirect(self, response: httpx.Response) -> None:
        """Abort before httpx follows a redirect off this source's domain."""
        if not response.has_redirect_location:
            return
        target = str(response.url.join(response.headers["location"]))
        reason = redirect_rejection_reason(target, self._redirect_hosts)
        if reason:
            raise ConnectorHttpError(f"Redirect blocked ({reason}).")

    def _rate_limit(self) -> None:
        with self._rate_lock:
            now = time.monotonic()
            elapsed = now - self._last_request
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_request = time.monotonic()

    def _retry_sleep(self, attempt: int, response: httpx.Response | None = None) -> None:
        if response is not None and response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    time.sleep(max(float(retry_after), 1.0))
                    return
                except ValueError:
                    pass
            time.sleep(min(8.0, 1.5 * (2**attempt)))
            return
        time.sleep(0.5 * (2**attempt))

    def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            self._rate_limit()
            try:
                response = self._client.get(path, params=_serialize_params(params))
                if response.status_code in RETRYABLE_STATUS:
                    if attempt + 1 < self._max_retries:
                        self._retry_sleep(attempt, response)
                    raise ConnectorHttpError(
                        f"Retryable HTTP {response.status_code}",
                        status_code=response.status_code,
                    )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ConnectorHttpError("Expected JSON object response.")
                return payload
            except (httpx.HTTPError, ConnectorHttpError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt + 1 >= self._max_retries:
                    break
                if not isinstance(exc, ConnectorHttpError) or exc.status_code not in RETRYABLE_STATUS:
                    self._retry_sleep(attempt)

        message = str(last_error) if last_error else "Unknown HTTP error"
        status_code = (
            last_error.status_code
            if isinstance(last_error, ConnectorHttpError)
            else None
        )
        raise ConnectorHttpError(message, status_code=status_code) from last_error

    def get_json_value(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Like ``get_json`` but accepts arrays and scalars."""
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            self._rate_limit()
            try:
                response = self._client.get(path, params=_serialize_params(params))
                if response.status_code in RETRYABLE_STATUS:
                    if attempt + 1 < self._max_retries:
                        self._retry_sleep(attempt, response)
                    raise ConnectorHttpError(
                        f"Retryable HTTP {response.status_code}",
                        status_code=response.status_code,
                    )
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ConnectorHttpError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt + 1 >= self._max_retries:
                    break
                if not isinstance(exc, ConnectorHttpError) or exc.status_code not in RETRYABLE_STATUS:
                    self._retry_sleep(attempt)

        message = str(last_error) if last_error else "Unknown HTTP error"
        status_code = (
            last_error.status_code
            if isinstance(last_error, ConnectorHttpError)
            else None
        )
        raise ConnectorHttpError(message, status_code=status_code) from last_error

    def get_text(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> str:
        """Fetch an HTML or plain-text document."""
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            self._rate_limit()
            try:
                response = self._client.get(path, params=_serialize_params(params))
                if response.status_code in RETRYABLE_STATUS:
                    raise ConnectorHttpError(
                        f"Retryable HTTP {response.status_code}",
                        status_code=response.status_code,
                    )
                response.raise_for_status()
                return response.text
            except (httpx.HTTPError, ConnectorHttpError) as exc:
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
        """POST form data and return the response text (used for AJAX endpoints)."""
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            self._rate_limit()
            try:
                headers = dict(self._client.headers)
                if extra_headers:
                    headers.update(extra_headers)
                response = self._client.post(path, data=data or {}, headers=headers)
                if response.status_code in RETRYABLE_STATUS:
                    raise ConnectorHttpError(
                        f"Retryable HTTP {response.status_code}",
                        status_code=response.status_code,
                    )
                response.raise_for_status()
                return response.text
            except (httpx.HTTPError, ConnectorHttpError) as exc:
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

    def get_bytes(self, url: str) -> tuple[str, bytes]:
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            self._rate_limit()
            try:
                response = self._client.get(url)
                if response.status_code in RETRYABLE_STATUS:
                    raise ConnectorHttpError(
                        f"Retryable HTTP {response.status_code}",
                        status_code=response.status_code,
                    )
                response.raise_for_status()
                media_type = response.headers.get("content-type", "image/jpeg").split(";")[0]
                return media_type, response.content
            except (httpx.HTTPError, ConnectorHttpError) as exc:
                last_error = exc
                if attempt + 1 >= self._max_retries:
                    break
                time.sleep(0.5 * (2**attempt))

        message = str(last_error) if last_error else "Unknown HTTP error"
        raise ConnectorHttpError(message) from last_error

    def close(self) -> None:
        self._client.close()
