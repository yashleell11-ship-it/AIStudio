"""Shared HTTP utilities for source connectors."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

DEFAULT_USER_AGENT = "AIStudio/0.1 (local manga reader; +https://github.com/aistudio)"
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


class AsyncConnectorHttpClient:
    """Rate-limited async HTTP client with retries for connector implementations."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        min_interval: float = 0.21,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._min_interval = min_interval
        self._user_agent = user_agent
        self._last_request = 0.0
        self._rate_lock = asyncio.Lock()
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                headers={
                    "User-Agent": self._user_agent,
                    "Accept": "application/json",
                },
                follow_redirects=True,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _rate_limit(self) -> None:
        async with self._rate_lock:
            now = time.monotonic()
            elapsed = now - self._last_request
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_request = time.monotonic()

    async def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        client = await self._get_client()
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            await self._rate_limit()
            try:
                response = await client.get(path, params=_serialize_params(params))
                if response.status_code in RETRYABLE_STATUS:
                    raise ConnectorHttpError(
                        f"Retryable HTTP {response.status_code}",
                        status_code=response.status_code,
                    )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ConnectorHttpError("Expected JSON object response.")
                return payload
            except (httpx.HTTPError, ConnectorHttpError) as exc:
                last_error = exc
                if attempt + 1 >= self._max_retries:
                    break
                await asyncio.sleep(0.5 * (2**attempt))

        message = str(last_error) if last_error else "Unknown HTTP error"
        status_code = (
            last_error.status_code
            if isinstance(last_error, ConnectorHttpError)
            else None
        )
        raise ConnectorHttpError(message, status_code=status_code) from last_error

    async def get_bytes(self, url: str) -> tuple[str, bytes]:
        client = await self._get_client()
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            await self._rate_limit()
            try:
                response = await client.get(url)
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
                await asyncio.sleep(0.5 * (2**attempt))

        message = str(last_error) if last_error else "Unknown HTTP error"
        raise ConnectorHttpError(message) from last_error


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
        request_headers = {
            "User-Agent": user_agent,
            "Accept": "application/json",
        }
        if headers:
            request_headers.update(headers)
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=self._timeout,
            headers=request_headers,
            follow_redirects=True,
        )

    @classmethod
    def from_async_client(cls, async_client: AsyncConnectorHttpClient) -> SyncConnectorHttpClient:
        """Build a sync client using the same settings as an async client."""
        return cls(
            async_client._base_url,
            timeout=async_client._timeout,
            max_retries=async_client._max_retries,
            min_interval=async_client._min_interval,
            user_agent=async_client._user_agent,
        )

    def _rate_limit(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.monotonic()

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
                    raise ConnectorHttpError(
                        f"Retryable HTTP {response.status_code}",
                        status_code=response.status_code,
                    )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ConnectorHttpError("Expected JSON object response.")
                return payload
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
