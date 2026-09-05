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
    """Raised when a connector HTTP request fails after retries.

    ``retryable`` overrides the status-based decision in ``is_retryable`` for
    the cases where the status alone is misleading — a Cloudflare interstitial
    is reported as 403 but is a *transient* block that a fresh TLS handshake
    genuinely can get past, unlike a 403 the origin means.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


#: Longest a ``Retry-After`` header may park this thread. The header is
#: attacker-controlled as far as we are concerned -- an origin answering
#: ``Retry-After: 3600`` would otherwise sleep a request thread for an hour,
#: and the caller has its own connector budget long before that.
MAX_RETRY_AFTER_SECONDS = 8.0


def status_of(exc: BaseException | None) -> int | None:
    """The upstream HTTP status behind a failure, whatever shape it arrived in.

    ``httpx.raise_for_status`` raises ``HTTPStatusError`` carrying the
    response; our own wrapper carries ``status_code``. Reading both here is
    what lets a connector write ``exc.status_code == 404`` instead of
    grepping the message text.
    """
    if isinstance(exc, ConnectorHttpError):
        return exc.status_code
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    return None


def is_retryable(exc: BaseException | None) -> bool:
    """Is trying this request again capable of a different answer?

    Transport failures (timeout, reset, DNS) and the overload/server statuses
    in ``RETRYABLE_STATUS`` are worth another attempt. A deterministic 4xx is
    not: 404 means gone, 400 means this endpoint does not accept this call,
    403 means blocked. Re-asking returns the identical answer.

    Measured on the VPS, retrying them was not free. Every Madara series page
    probes ``/wp-admin/admin-ajax.php`` first; on cocomic, cucumbermanga,
    lilymanga, manhwatop and manhuanext that endpoint answers 400/403, and the
    old loop spent three round trips plus 0.5s + 1.0s of backoff *sleep* to
    learn it again — 2.5-3.2s of the detail stage, on every series open.
    """
    override = getattr(exc, "retryable", None)
    if override is not None:
        return bool(override)
    status = status_of(exc)
    if status is None:
        # A transport-level failure (httpx.TimeoutException, ConnectError,
        # a JSON body that did not parse) — genuinely worth another attempt.
        return True
    return status in RETRYABLE_STATUS


class SyncConnectorHttpClient:
    """Sync HTTP client with retries for connector implementations."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        min_interval: float = 0.21,
        burst: int = 1,
        user_agent: str = DEFAULT_USER_AGENT,
        headers: dict[str, str] | None = None,
        extra_redirect_hosts: frozenset[str] | set[str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._min_interval = min_interval
        # How many requests may leave together before the interval applies.
        # Raise it ONLY on a connector that deliberately fans out (see
        # _rate_limit); the long-run rate is the same either way.
        self._burst = max(1, int(burst))
        self._tokens = float(self._burst)
        self._token_clock = time.monotonic()
        self._rate_lock = threading.Lock()
        request_headers = {
            "User-Agent": user_agent,
            "Accept": "application/json",
        }
        if headers:
            request_headers.update(headers)
        self._redirect_hosts = allowed_redirect_hosts(
            self._base_url, extra_redirect_hosts
        )
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
        """Space requests out, allowing up to ``burst`` of them to go at once.

        A token bucket, not a hard gap. The gap version held the lock across
        its own ``sleep``, so a connector that deliberately fans out — webtoons
        fetches six episode-list pages on a ThreadPoolExecutor, e-hentai four
        thumbnail pages — had its parallelism cancelled by this method: the six
        threads queued behind each other 0.21s apart and the batch took longer
        than the requests did. Measured from the VPS, webtoons' chapter stage
        spent ~2.3s of its 3.75s waiting here rather than on the network.

        With ``burst=1`` (the default, and what every non-fanning connector
        keeps) the behaviour is the old one. Above that, a batch goes out
        together and then refills at exactly the same long-run rate, so the
        politeness budget the interval encodes is unchanged.
        """
        if self._min_interval <= 0:
            return
        while True:
            with self._rate_lock:
                now = time.monotonic()
                # Refill: one token per min_interval, capped at the burst size.
                self._tokens = min(
                    float(self._burst),
                    self._tokens + (now - self._token_clock) / self._min_interval,
                )
                self._token_clock = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) * self._min_interval
            # Slept OUTSIDE the lock, so waiting threads do not serialize on
            # each other's sleeps the way the old gap-based limiter did.
            time.sleep(wait)

    def _retry_sleep(self, attempt: int, response: httpx.Response | None = None) -> None:
        if response is not None and response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    # Clamped: an origin is free to ask for an hour, and a
                    # request thread parked that long is a hang, not a retry.
                    time.sleep(
                        min(MAX_RETRY_AFTER_SECONDS, max(float(retry_after), 1.0))
                    )
                    return
                except ValueError:
                    pass
            time.sleep(min(MAX_RETRY_AFTER_SECONDS, 1.5 * (2**attempt)))
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
                if not is_retryable(exc):
                    break
                if attempt + 1 >= self._max_retries:
                    break
                if not isinstance(exc, ConnectorHttpError) or exc.status_code not in RETRYABLE_STATUS:
                    self._retry_sleep(attempt)

        message = str(last_error) if last_error else "Unknown HTTP error"
        raise ConnectorHttpError(
            message, status_code=status_of(last_error)
        ) from last_error

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
                if not is_retryable(exc):
                    break
                if attempt + 1 >= self._max_retries:
                    break
                if not isinstance(exc, ConnectorHttpError) or exc.status_code not in RETRYABLE_STATUS:
                    self._retry_sleep(attempt)

        message = str(last_error) if last_error else "Unknown HTTP error"
        raise ConnectorHttpError(
            message, status_code=status_of(last_error)
        ) from last_error

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
                if not is_retryable(exc):
                    break
                if attempt + 1 >= self._max_retries:
                    break
                time.sleep(0.5 * (2**attempt))

        message = str(last_error) if last_error else "Unknown HTTP error"
        raise ConnectorHttpError(
            message, status_code=status_of(last_error)
        ) from last_error

    def post_text(
        self,
        path: str,
        *,
        data: dict[str, str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> str:
        """POST form data and return the response text (used for AJAX endpoints).

        Only ``extra_headers`` is handed to httpx. The client's configured
        headers still reach the wire -- httpx merges them in itself -- and
        letting it do that merge is the whole point. ``httpx.Headers`` keeps a
        lowercased lookup key beside each raw name, so ``dict(client.headers)``
        hands back ``user-agent`` / ``accept`` / ``accept-encoding`` /
        ``connection``, and re-supplying that dict (which this method used to
        do) put those lowercase names on the wire.

        Measured from the VPS against elftoon and rawkuma, both behind
        Cloudflare: lowercasing ANY ONE of ``Accept-Encoding``, ``Connection``,
        ``User-Agent`` or ``Accept`` turns a 200 into a 403 "Just a moment"
        interstitial in 8-26 ms. Header casing is part of what Cloudflare
        fingerprints against the browser the User-Agent claims to be.
        ``Accept-Language``, ``Referer`` and ``X-Requested-With`` were
        indifferent -- so this is not a general "explicit headers" rule, it is
        those four standard names specifically.

        Re-supplying the dict also DUPLICATED every header a connector
        overrode: a plain dict treats ``accept`` and ``Accept`` as two keys, so
        the Madara AJAX call shipped both the client's ``accept:`` and its own
        ``Accept: */*``.

        Connector-supplied names are passed through untouched. They are already
        written the way a browser writes them, and some are deliberately not
        title-case (``X-CSRF-TOKEN``).
        """
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            self._rate_limit()
            try:
                response = self._client.post(
                    path, data=data or {}, headers=extra_headers or None
                )
                if response.status_code in RETRYABLE_STATUS:
                    raise ConnectorHttpError(
                        f"Retryable HTTP {response.status_code}",
                        status_code=response.status_code,
                    )
                response.raise_for_status()
                return response.text
            except (httpx.HTTPError, ConnectorHttpError) as exc:
                last_error = exc
                if not is_retryable(exc):
                    break
                if attempt + 1 >= self._max_retries:
                    break
                time.sleep(0.5 * (2**attempt))

        message = str(last_error) if last_error else "Unknown HTTP error"
        raise ConnectorHttpError(
            message, status_code=status_of(last_error)
        ) from last_error

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
                if not is_retryable(exc):
                    break
                if attempt + 1 >= self._max_retries:
                    break
                time.sleep(0.5 * (2**attempt))

        message = str(last_error) if last_error else "Unknown HTTP error"
        raise ConnectorHttpError(
            message, status_code=status_of(last_error)
        ) from last_error

    def close(self) -> None:
        self._client.close()
