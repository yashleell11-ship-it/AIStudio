"""HTTP client for 1stkissmanga.io anti-bot fingerprint gate."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from connectors.http.cf_client import CfSyncHttpClient, is_cloudflare_challenge
from connectors.http.client import ConnectorHttpError

_REDIRECT_LINK_RE = re.compile(r"redirect_link\s*=\s*'([^']+)'")
_FINGERPRINT_MARKERS = ("fingerprintjs", "redirect_link")
_PARKING_MARKERS = (
    "parklogic.com",
    "resources and information",
    "ww16.",
    "router.parklogic",
)


def is_fingerprint_gate(html: str) -> bool:
    """Return True when HTML is the FingerprintJS interstitial, not catalog content."""
    lowered = html.lower()
    if "page-item-detail" in lowered or "wp-manga-chapter" in lowered:
        return False
    return all(marker in lowered for marker in _FINGERPRINT_MARKERS)


def is_parking_page(html: str, *, url: str) -> bool:
    """Detect domain-parking / ad interstitials that replace the Madara catalog."""
    lowered = html.lower()
    host = urlparse(url).netloc.casefold()
    if host.startswith("ww16.") or host.startswith("ww38."):
        return True
    return any(marker in lowered for marker in _PARKING_MARKERS)


class FirstKissHttpClient(CfSyncHttpClient):
    """curl_cffi client that clears the site's FingerprintJS redirect gate."""

    _GATE_SUFFIX = "fp=-7"

    def get_text(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> str:
        html = super().get_text(path, params=params)
        if is_fingerprint_gate(html):
            html = self._pass_fingerprint_gate(html)
        if is_parking_page(html, url=path):
            raise ConnectorHttpError(
                "1stkissmanga.io redirected to a parking page instead of catalog content.",
                status_code=403,
            )
        if is_cloudflare_challenge(html):
            raise ConnectorHttpError(
                "Cloudflare challenge blocked the request.",
                status_code=403,
            )
        return html

    def _pass_fingerprint_gate(self, gate_html: str) -> str:
        match = _REDIRECT_LINK_RE.search(gate_html)
        if match is None:
            raise ConnectorHttpError(
                "Fingerprint gate missing redirect target.",
                status_code=403,
            )
        bypass_url = match.group(1) + self._GATE_SUFFIX
        if bypass_url.startswith("http://"):
            bypass_url = "https://" + bypass_url.removeprefix("http://")

        self._rate_limit()
        response = self._session.get(
            bypass_url,
            headers=self._headers,
            timeout=self._timeout,
            allow_redirects=True,
        )
        if response.status_code >= 400:
            raise ConnectorHttpError(
                f"Fingerprint bypass failed with HTTP {response.status_code}.",
                status_code=response.status_code,
            )
        html = response.text
        if is_fingerprint_gate(html):
            raise ConnectorHttpError(
                "Fingerprint gate still active after bypass attempt.",
                status_code=403,
            )
        if is_parking_page(html, url=response.url):
            raise ConnectorHttpError(
                "1stkissmanga.io redirected to a parking page instead of catalog content.",
                status_code=403,
            )
        return html
