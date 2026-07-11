"""HTTP client for 1stkissmanga.io anti-bot gates (FingerprintJS and Cheq)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse, urlsplit

from connectors.http.cf_client import CfSyncHttpClient, is_cloudflare_challenge
from connectors.http.client import ConnectorHttpError

_REDIRECT_LINK_RE = re.compile(r"redirect_link\s*=\s*'([^']+)'")
_CHEQ_REDIRECT_RE = re.compile(r"REDIRECT_URL\s*=\s*'([^']+)'")
_FINGERPRINT_MARKERS = ("fingerprintjs", "redirect_link")
_CHEQ_MARKERS = ("cheqrequestid", "brandsmat.com")
_CATALOG_MARKERS = ("page-item-detail", "wp-manga-chapter", "c-tabs-item__content")
_PARKING_MARKERS = (
    "parklogic.com",
    "resources and information",
    "router.parklogic",
    "sedoparking.com",
    "domain may be for sale",
)
_PARKING_HOST_PREFIXES = ("ww16.", "ww38.")


def is_fingerprint_gate(html: str) -> bool:
    """Return True when HTML is the FingerprintJS interstitial, not catalog content."""
    lowered = html.lower()
    if _has_catalog_markers(lowered):
        return False
    return all(marker in lowered for marker in _FINGERPRINT_MARKERS)


def is_cheq_gate(html: str) -> bool:
    """Return True when HTML is the Cheq/Brandsafe interstitial."""
    lowered = html.lower()
    if _has_catalog_markers(lowered):
        return False
    return all(marker in lowered for marker in _CHEQ_MARKERS) and "redirect_url" in lowered


def is_bot_gate(html: str) -> bool:
    """Return True when HTML is an anti-bot interstitial rather than catalog content."""
    return is_fingerprint_gate(html) or is_cheq_gate(html)


def is_catalog_html(html: str) -> bool:
    """Return True when HTML looks like a Madara browse/detail/chapter page."""
    return _has_catalog_markers(html.lower())


def _has_catalog_markers(lowered_html: str) -> bool:
    return any(marker in lowered_html for marker in _CATALOG_MARKERS)


def is_parking_page(html: str, *, url: str) -> bool:
    """Detect domain-parking / ad interstitials that replace the Madara catalog."""
    lowered = html.lower()
    host = urlparse(url).netloc.casefold()
    if any(host.startswith(prefix) for prefix in _PARKING_HOST_PREFIXES):
        return True
    return any(marker in lowered for marker in _PARKING_MARKERS)


class FirstKissHttpClient(CfSyncHttpClient):
    """curl_cffi client that clears the site's anti-bot redirect gates."""

    # fp=-7 is the JS timeout fallback and routes bots to ww16 parking; fp=-3 is
    # the manual bypass token exposed in the Cheq interstitial hidden link.
    _GATE_FP = "-3"
    _MAX_GATE_HOPS = 4

    def get_text(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> str:
        html, final_url = self._fetch_html(path, params=params)
        if is_bot_gate(html):
            html, final_url = self._pass_bot_gate(html)
        self._validate_catalog_html(html, url=final_url)
        return html

    def _fetch_html(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        url = self._resolve_url(path)
        self._rate_limit()
        response = self._session.get(
            url,
            params=params,
            headers=self._headers,
            timeout=self._timeout,
            allow_redirects=True,
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
        return html, str(response.url)

    def _bypass_url_from_gate(self, gate_html: str) -> str:
        match = _REDIRECT_LINK_RE.search(gate_html)
        if match is None:
            match = _CHEQ_REDIRECT_RE.search(gate_html)
        if match is None:
            raise ConnectorHttpError(
                "Anti-bot gate missing redirect target.",
                status_code=403,
            )
        bypass_url = match.group(1)
        bypass_url = self._with_gate_fp(bypass_url, self._GATE_FP)
        if bypass_url.startswith("http://"):
            bypass_url = "https://" + bypass_url.removeprefix("http://")
        return bypass_url

    @staticmethod
    def _with_gate_fp(url: str, fp: str) -> str:
        if "fp=" in url:
            return re.sub(r"fp=[^&'\"]*", f"fp={fp}", url, count=1)
        return f"{url}fp={fp}"

    def _pass_bot_gate(self, gate_html: str) -> tuple[str, str]:
        html = gate_html
        final_url = self._base_url
        for _ in range(self._MAX_GATE_HOPS):
            if not is_bot_gate(html):
                break
            bypass_url = self._bypass_url_from_gate(html)
            html, final_url = self._fetch_html_url(bypass_url)
            if is_parking_page(html, url=final_url):
                raise ConnectorHttpError(
                    "1stkissmanga.io redirected to a parking page instead of catalog content.",
                    status_code=403,
                )
        if is_bot_gate(html):
            raise ConnectorHttpError(
                "Anti-bot gate still active after bypass attempt.",
                status_code=403,
            )
        return html, final_url

    def _fetch_html_url(self, url: str) -> tuple[str, str]:
        self._rate_limit()
        response = self._session.get(
            url,
            headers=self._headers,
            timeout=self._timeout,
            allow_redirects=True,
        )
        if response.status_code >= 400:
            raise ConnectorHttpError(
                f"Anti-bot bypass failed with HTTP {response.status_code}.",
                status_code=response.status_code,
            )
        final_url = str(response.url)
        if self._is_parking_host(final_url):
            raise ConnectorHttpError(
                "1stkissmanga.io redirected to a parking page instead of catalog content.",
                status_code=403,
            )
        return response.text, final_url

    @staticmethod
    def _is_parking_host(url: str) -> bool:
        host = urlsplit(url).netloc.casefold()
        return any(host.startswith(prefix) for prefix in _PARKING_HOST_PREFIXES)

    def _validate_catalog_html(self, html: str, *, url: str) -> None:
        if is_parking_page(html, url=url):
            raise ConnectorHttpError(
                "1stkissmanga.io redirected to a parking page instead of catalog content.",
                status_code=403,
            )
        if is_cloudflare_challenge(html):
            raise ConnectorHttpError(
                "Cloudflare challenge blocked the request.",
                status_code=403,
            )
        if is_bot_gate(html):
            raise ConnectorHttpError(
                "Anti-bot gate blocked the request.",
                status_code=403,
            )
        if not is_catalog_html(html):
            raise ConnectorHttpError(
                "1stkissmanga.io returned unrecognized HTML (site may be down or parked).",
                status_code=403,
            )
