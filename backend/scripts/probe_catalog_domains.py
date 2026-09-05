#!/usr/bin/env python3
"""HTTP probe every catalog domain; classify Madara vs custom vs dead.

Runs before connector-level probes to detect sites that need dedicated
connectors instead of the Madara factory.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from connectors.catalog import HANDCRAFTED_CONNECTORS, MADARA_CATALOG  # noqa: E402
from connectors.registry import list_installed_connectors  # noqa: E402

RESULTS_PATH = BACKEND.parent / "docs" / "catalog_domain_probe.json"
CONNECTOR_RESULTS = BACKEND.parent / "docs" / "connector_probe_results.json"
MAX_WORKERS = 8
TIMEOUT = 20.0

HANDCRAFTED = HANDCRAFTED_CONNECTORS
# Asking the registry beats a hand-kept literal here: the previous one named a
# single source, so every other adult handcrafted row printed as safe.
MATURE_SOURCE_IDS = frozenset(
    d.source_type for d in list_installed_connectors() if d.mature
)
EXCLUDED = frozenset({"comick"})

MADARA_MARKERS = (
    "wp-manga",
    "page-item-detail",
    "c-tabs-item__content",
    "madara",
    "wp-manga-chapter",
)
SPA_MARKERS = ("__NEXT_DATA__", "_next/static", "react-root", "ng-version")
API_MARKERS = ('"/api/', "'/api/", "application/json")


@dataclass
class DomainProbeResult:
    source_id: str
    domain: str
    mature: bool
    url_segment: str
    classification: str  # TRUE_MADARA | CUSTOM_NEEDED | DEAD | UNREACHABLE | HANDCRAFTED
    http_status: int | None = None
    listing_cards: int = 0
    markers: str = ""
    detail: str = ""
    strikes: int = 0


def _fetch(base_url: str, path: str, *, use_cf: bool) -> tuple[int | None, str, str]:
    """Return (status, body snippet, error detail)."""
    headers = {"Accept": "text/html,application/xhtml+xml"}
    try:
        if use_cf:
            from connectors.http.cf_client import CfSyncHttpClient

            client = CfSyncHttpClient(
                base_url,
                headers=headers,
                impersonate="chrome131",
                timeout=TIMEOUT,
            )
            try:
                text = client.get_text(path)
            finally:
                client.close()
            return 200, text[:120_000], ""
        import httpx

        resp = httpx.get(
            f"{base_url.rstrip('/')}/{path.lstrip('/')}",
            headers=headers,
            follow_redirects=True,
            timeout=TIMEOUT,
        )
        text = resp.text[:120_000] if resp.text else ""
        return resp.status_code, text, ""
    except Exception as exc:
        from connectors.http.client import ConnectorHttpError

        if isinstance(exc, ConnectorHttpError):
            return exc.status_code, "", str(exc)[:200]
        return None, "", f"{type(exc).__name__}: {exc}"[:200]


def _count_listing_cards(html: str, url_segment: str) -> int:
    pattern = re.compile(
        rf'class="page-item-detail[^"]*"[^>]*>.*?/{url_segment}/[a-z0-9-]+/',
        re.I | re.S,
    )
    return len(pattern.findall(html))


def _detect_markers(html: str) -> list[str]:
    lower = html.lower()
    found: list[str] = []
    for marker in MADARA_MARKERS:
        if marker in lower:
            found.append(f"madara:{marker}")
    for marker in SPA_MARKERS:
        if marker.lower() in lower:
            found.append(f"spa:{marker}")
    for marker in API_MARKERS:
        if marker in html:
            found.append(f"api:{marker}")
    return found


def _load_strikes() -> dict[str, int]:
    strikes: dict[str, int] = {}
    if CONNECTOR_RESULTS.exists():
        data = json.loads(CONNECTOR_RESULTS.read_text(encoding="utf-8"))
        for row in data.get("results", []):
            if row.get("status") in ("DEAD", "ERROR"):
                strikes[row["source_id"]] = strikes.get(row["source_id"], 0) + 1
    if RESULTS_PATH.exists():
        data = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        for row in data.get("results", []):
            if row.get("classification") in ("DEAD", "UNREACHABLE"):
                strikes[row["source_id"]] = strikes.get(row["source_id"], 0) + 1
    return strikes


def _probe_site(
    source_id: str,
    domain: str,
    *,
    mature: bool,
    url_segment: str,
    use_cf: bool,
    strikes: dict[str, int],
) -> DomainProbeResult:
    if source_id in HANDCRAFTED:
        return DomainProbeResult(
            source_id=source_id,
            domain=domain,
            mature=mature,
            url_segment=url_segment,
            classification="HANDCRAFTED",
            detail="registered custom connector",
        )

    base = f"https://{domain}"
    status, body, err = _fetch(base, f"/{url_segment}/", use_cf=use_cf)
    if not body and (status is None or status >= 400):
        home_status, home_body, home_err = _fetch(base, "/", use_cf=use_cf)
        if home_body:
            status, body, err = home_status, home_body, home_err
        elif status is None:
            status, err = home_status, home_err or err

    if status is None:
        return DomainProbeResult(
            source_id=source_id,
            domain=domain,
            mature=mature,
            url_segment=url_segment,
            classification="UNREACHABLE",
            detail=err[:200],
            strikes=strikes.get(source_id, 0) + 1,
        )

    if status >= 400:
        return DomainProbeResult(
            source_id=source_id,
            domain=domain,
            mature=mature,
            url_segment=url_segment,
            classification="DEAD",
            http_status=status,
            detail=f"http {status}",
            strikes=strikes.get(source_id, 0) + 1,
        )

    markers = _detect_markers(body)
    cards = _count_listing_cards(body, url_segment)

    madara_hits = [m for m in markers if m.startswith("madara:")]
    spa_hits = [m for m in markers if m.startswith("spa:")]
    api_hits = [m for m in markers if m.startswith("api:")]

    if madara_hits and cards >= 3:
        classification = "TRUE_MADARA"
    elif madara_hits and cards > 0:
        classification = "TRUE_MADARA"
    elif api_hits or spa_hits:
        classification = "CUSTOM_NEEDED"
    elif cards >= 3:
        classification = "CUSTOM_NEEDED"
    elif len(body) < 500:
        classification = "DEAD"
    else:
        classification = "CUSTOM_NEEDED"

    return DomainProbeResult(
        source_id=source_id,
        domain=domain,
        mature=mature,
        url_segment=url_segment,
        classification=classification,
        http_status=status,
        listing_cards=cards,
        markers=", ".join(markers[:6]),
        detail="" if classification != "DEAD" else "no recognizable listing",
        strikes=strikes.get(source_id, 0) + (1 if classification in ("DEAD", "UNREACHABLE") else 0),
    )


# ---------------------------------------------------------------------------
# Candidate-domain mode
#
# The catalog mode above answers "is a source we already ship still alive?".
# This mode answers the prior question -- "is this domain worth shipping at
# all?" -- for a list of domains nobody has written a config for yet, so it
# has to discover the URL segment and image hosts the catalog mode is handed.
# ---------------------------------------------------------------------------

VPS_HOST = "ubuntu@135.148.43.147"
VPS_CONTAINER = "manhwamaniacs-backend"
CANDIDATE_RESULTS = BACKEND.parent / "docs" / "mature_candidate_probe.json"

# Ordered by how often a Madara install actually uses them, because the
# discovery loop stops at the first segment that yields cards and every extra
# guess is a 20s worst case against a site that may already be rate-limiting.
CANDIDATE_SEGMENTS = (
    "manga", "comics", "webtoon", "manhwa", "manhua", "series", "comic",
    "porncomic", "read", "novel",
)

# Whole-domain wall clock. A probe that never returns is the failure mode
# that matters here; a wrong classification can be re-probed.
CANDIDATE_BUDGET = 75.0

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

PARKED_MARKERS = (
    "sedoparking", "parkingcrew", "afternic", "hugedomains", "dan.com",
    "bodis.com", "domain is for sale", "buy this domain", "this domain may be",
    "domain for sale", "registration has expired", "renew now", "godaddy.com/forsale",
    "namecheap.com/domains/registration", "domainmarket", "sav.com",
    "checking your browser", "related searches", "sponsored listings",
)
CF_CHALLENGE_MARKERS = (
    "just a moment", "cf_chl_opt", "cf-browser-verification", "challenge-platform",
    "attention required! | cloudflare", "enable javascript and cookies to continue",
)
CF_BLOCK_MARKERS = ("sorry, you have been blocked", "you are unable to access")

# Presence proves adult intent; absence does not disprove it, so the report
# records the hits rather than flipping a boolean off.
ADULT_MARKERS = (
    "hentai", "porn", "nsfw", "18+", "adult", "ecchi", "smut", "doujin",
    "xxx", "erotic", "mature content", "age verification", "uncensored",
    "yaoi", "yuri", "netorare", "rape", "incest", "harem",
)

THEMESIA_MARKERS = ("themesia", "bixbox", "ts_reader", "listupd", "bsx", "epcurlast")
WP_MARKERS = ("wp-content", "wp-includes", "wp-json")


@dataclass
class CandidateResult:
    domain: str
    name: str
    kind: str
    claimed_mature: bool
    suspected_cms: str
    outcome: str  # MADARA | BESPOKE | CF_BLOCKED | CF_CHALLENGE | PARKED | DEAD | NXDOMAIN | TIMEOUT | DUPLICATE
    http_status: int | None = None
    final_host: str = ""
    title: str = ""
    server: str = ""
    reachable: bool = False
    real_catalogue: bool = False
    cms: str = "unknown"
    needs_cf: bool = False
    url_segment: str = ""
    listing_post_type: str | None = None
    listing_cards: int = 0
    chapter_mechanism: str = ""
    image_hosts: list[str] = field(default_factory=list)
    page_images: int = 0
    adult_signals: list[str] = field(default_factory=list)
    duplicate_of: str = ""
    detail: str = ""


def _registered_hosts() -> dict[str, str]:
    """Map every host this repo already fetches from -> the source that owns it.

    Four sources were withdrawn for serving a backend the app already had, so
    a candidate that redirects onto a registered host has to be caught here
    rather than after a connector is written for it.
    """
    hosts: dict[str, str] = {}
    for cfg in MADARA_CATALOG:
        hosts[cfg.site_host] = cfg.source_id
        for extra in cfg.extra_image_hosts:
            hosts[extra.lower()] = cfg.source_id
    url_re = re.compile(r'https?://([a-z0-9.-]+\.[a-z]{2,})', re.I)
    for path in (BACKEND / "connectors").rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        owner = path.parent.name if path.parent.name != "connectors" else path.stem
        for host in url_re.findall(text):
            hosts.setdefault(host.lower(), owner)
    return hosts


def _registrable(host: str) -> str:
    parts = host.lower().lstrip(".").split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host.lower()


class _Fetcher:
    """One bounded HTTP surface per candidate, plus a curl_cffi second chance.

    Every call is capped twice -- per request and against a whole-domain
    deadline -- because the failure mode that matters here is not a wrong
    answer, it is a probe that never returns.
    """

    def __init__(self, deadline: float) -> None:
        import httpx

        self.deadline = deadline
        self.client = httpx.Client(
            headers=BROWSER_HEADERS,
            follow_redirects=True,
            timeout=httpx.Timeout(TIMEOUT, connect=10.0),
            verify=False,
        )

    def close(self) -> None:
        self.client.close()

    def expired(self) -> bool:
        return time.monotonic() > self.deadline

    def get(self, url: str, *, use_cf: bool = False) -> tuple[int | None, str, str, str]:
        """Return (status, text, final_host, error)."""
        if self.expired():
            return None, "", "", "deadline exceeded"
        if use_cf:
            try:
                from curl_cffi import requests as cffi_requests

                resp = cffi_requests.get(
                    url,
                    headers=BROWSER_HEADERS,
                    impersonate="chrome131",
                    timeout=TIMEOUT,
                    allow_redirects=True,
                    verify=False,
                )
                host = urlparse(str(resp.url)).hostname or ""
                return resp.status_code, (resp.text or "")[:400_000], host.lower(), ""
            except Exception as exc:
                return None, "", "", f"{type(exc).__name__}: {exc}"[:180]
        try:
            resp = self.client.get(url)
            host = urlparse(str(resp.url)).hostname or ""
            return resp.status_code, (resp.text or "")[:400_000], host.lower(), ""
        except Exception as exc:
            return None, "", "", f"{type(exc).__name__}: {exc}"[:180]


def _title_of(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip()[:120] if m else ""


def _hits(html_lower: str, markers: tuple[str, ...]) -> list[str]:
    return [m for m in markers if m in html_lower]


def _detect_cms(html: str) -> str:
    low = html.lower()
    if "themes/madara" in low or "wp-manga" in low or "madara" in low:
        return "madara"
    if any(m in low for m in THEMESIA_MARKERS):
        return "themesia"
    if "__next_data__" in low or "_next/static" in low:
        return "nextjs"
    if any(m in low for m in WP_MARKERS):
        return "wordpress"
    if "list-manga" in low and "/comic/" in low:
        return "porncomic18-like"
    return "unknown"


_HREF_RE = re.compile(r"""<a\b[^>]*?\bhref\s*=\s*["\']([^"\'#][^"\']*)["\']""", re.I)
_IMG_RE = re.compile(
    r"""<img\b[^>]*?\b(?:data-src|data-lazy-src|data-original|src)\s*=\s*["\']([^"\']+)["\']""",
    re.I,
)


def _same_host_paths(html: str, host: str) -> list[str]:
    """Every same-host link as a normalised path.

    Half these sites emit ``href="/manga/slug"`` rather than an absolute URL,
    so matching only absolute URLs reported real catalogues as empty.
    """
    paths: list[str] = []
    for raw in _HREF_RE.findall(html):
        raw = raw.strip()
        if raw.startswith("//"):
            raw = "https:" + raw
        if raw.lower().startswith(("http://", "https://")):
            parsed = urlparse(raw)
            link_host = (parsed.hostname or "").lower()
            if _registrable(link_host) != _registrable(host):
                continue
            path = parsed.path
        elif raw.startswith("/"):
            path = raw
        else:
            continue
        if path and path != "/":
            paths.append(path.rstrip("/").lower())
    return paths


def _guess_segment(html: str, host: str) -> tuple[str, int]:
    """Pick the series path segment from the links a Madara listing emits."""
    counts: dict[str, int] = {}
    for path in _same_host_paths(html, host):
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2 and parts[0] in CANDIDATE_SEGMENTS and len(parts[1]) >= 3:
            counts[parts[0]] = counts.get(parts[0], 0) + 1
    if not counts:
        return "", 0
    best = max(counts.items(), key=lambda kv: kv[1])
    return best[0], best[1]


def _series_links(html: str, host: str, segment: str) -> list[str]:
    seen: list[str] = []
    for path in _same_host_paths(html, host):
        parts = [p for p in path.split("/") if p]
        if len(parts) == 2 and parts[0] == segment and len(parts[1]) >= 3:
            url = f"https://{host}/{segment}/{parts[1]}/"
            if url not in seen:
                seen.append(url)
    return seen


def _img_hosts(html: str, host: str) -> tuple[list[str], int]:
    """Return (off-site image hosts, count of image-looking <img> sources)."""
    hosts: list[str] = []
    count = 0
    for src in _IMG_RE.findall(html):
        src = src.strip()
        if src.startswith("//"):
            src = "https:" + src
        if src.lower().startswith(("http://", "https://")):
            img_host = (urlparse(src).hostname or "").lower()
            path = urlparse(src).path
        elif src.startswith("/"):
            img_host, path = host, src
        elif src.lower().startswith("data:"):
            continue
        else:
            img_host, path = host, "/" + src
        if not re.search(r"\.(jpe?g|png|webp|avif|gif)(\?|$)", path, re.I):
            continue
        count += 1
        if img_host and img_host not in hosts:
            hosts.append(img_host)
    return hosts, count


def _probe_candidate(entry: dict, registered: dict[str, str]) -> CandidateResult:
    domain = entry["domain"].strip().lower()
    res = CandidateResult(
        domain=domain,
        name=entry.get("name", ""),
        kind=entry.get("kind", ""),
        claimed_mature=bool(entry.get("mature")),
        suspected_cms=entry.get("suspected_cms", "unknown"),
        outcome="DEAD",
    )
    fetcher = _Fetcher(deadline=time.monotonic() + CANDIDATE_BUDGET)
    try:
        status, html, final_host, err = fetcher.get(f"https://{domain}/")
        low = html.lower()

        # A fingerprint block and an IP block look identical over plain httpx;
        # only the curl_cffi retry separates "needs use_cf=True" from "this
        # egress is banned", and that difference decides whether the source is
        # shippable at all.
        if status in (403, 429, 503) or (status is None and err) or _hits(low, CF_CHALLENGE_MARKERS):
            cf_status, cf_html, cf_host, cf_err = fetcher.get(f"https://{domain}/", use_cf=True)
            if cf_status == 200 and cf_html:
                res.needs_cf = True
                status, html, final_host, err = cf_status, cf_html, cf_host, ""
                low = html.lower()
            elif status is None:
                err = err or cf_err
                status = cf_status if cf_status is not None else status

        res.http_status = status
        res.final_host = final_host
        res.detail = err

        if status is None:
            low_err = err.lower()
            if "getaddrinfo" in low_err or "name or service not known" in low_err or "nodename" in low_err:
                res.outcome = "NXDOMAIN"
            elif "timeout" in low_err or "timed out" in low_err:
                res.outcome = "TIMEOUT"
            else:
                res.outcome = "UNREACHABLE"
            return res

        res.title = _title_of(html)
        res.adult_signals = _hits(low, ADULT_MARKERS)[:8]

        if status >= 400 or not html:
            if _hits(low, CF_BLOCK_MARKERS) or (status == 403 and "cloudflare" in low):
                res.outcome = "CF_BLOCKED"
            elif _hits(low, CF_CHALLENGE_MARKERS):
                res.outcome = "CF_CHALLENGE"
            else:
                res.outcome = "DEAD"
                res.detail = res.detail or f"http {status}"
            return res

        if _hits(low, CF_CHALLENGE_MARKERS):
            res.outcome = "CF_CHALLENGE"
            res.detail = "interstitial survives curl_cffi impersonation"
            return res
        if _hits(low, CF_BLOCK_MARKERS):
            res.outcome = "CF_BLOCKED"
            return res

        res.reachable = True

        parked = _hits(low, PARKED_MARKERS)
        if parked or len(html) < 1500:
            res.outcome = "PARKED"
            res.detail = f"parked markers: {', '.join(parked[:3])}" if parked else "body under 1.5 KB"
            return res

        if final_host and _registrable(final_host) != _registrable(domain):
            owner = registered.get(final_host) or registered.get(_registrable(final_host), "")
            if owner:
                res.outcome = "DUPLICATE"
                res.duplicate_of = owner
                res.detail = f"redirects to {final_host}, already served by {owner}"
                return res

        owner = registered.get(domain) or registered.get(_registrable(domain), "")
        if owner:
            res.outcome = "DUPLICATE"
            res.duplicate_of = owner
            res.detail = f"already registered as {owner}"
            return res

        res.cms = _detect_cms(html)
        host = final_host or domain
        if _registrable(host) != _registrable(domain):
            res.detail = f"redirects to {host}"

        # A WordPress home page can be a landing page with none of the theme's
        # markup on it, so a domain the discovery pass called Madara still gets
        # the segment hunt -- that hunt is where the one-line configs come from.
        if res.cms == "madara" or (res.suspected_cms == "madara" and res.cms == "wordpress"):
            _probe_madara(res, fetcher, host, html)
        else:
            _probe_bespoke(res, fetcher, host, html)
        return res
    finally:
        fetcher.close()


def _probe_bespoke(res: CandidateResult, fetcher: _Fetcher, host: str, html: str) -> None:
    """Decide whether a non-Madara 200 is a catalogue or just a page that loads.

    An affiliate hub, a parked lander and a real reader all answer 200, so the
    bar is a repeating series-link structure -- and because a client-rendered
    site serves none of that in its shell, one listing path is tried before
    the domain is called empty.
    """
    def _score(body: str) -> tuple[int, int, list[str]]:
        paths = _same_host_paths(body, host)
        deep = {p for p in paths if len([x for x in p.split("/") if x]) >= 2}
        hosts, imgs = _img_hosts(body, host)
        return len(deep), imgs, hosts

    links, imgs, hosts = _score(html)
    tried = ""
    if links < 10 and not fetcher.expired():
        # Order matters: the first path that is actually a listing wins, and
        # every extra guess is a 20s worst case against the same origin.
        for path in ("/list-manga", "/manga", "/comics", "/browse", "/series"):
            if fetcher.expired():
                break
            status, body, _h, _e = fetcher.get(f"https://{host}{path}", use_cf=res.needs_cf)
            if status == 200 and body:
                l2, i2, h2 = _score(body)
                if l2 > links:
                    links, imgs, hosts, tried = l2, i2, h2, path
                if l2 >= 10:
                    break

    res.listing_cards = links
    res.page_images = imgs
    res.image_hosts = [h for h in hosts if h and _registrable(h) != _registrable(host)][:6]
    res.real_catalogue = links >= 10 and imgs >= 8
    if res.real_catalogue:
        res.outcome = "BESPOKE"
        res.detail = f"catalogue at {tried or '/'}"
    elif res.cms == "nextjs" or "__next_data__" in html.lower():
        res.outcome = "SPA"
        res.detail = f"client-rendered shell, {links} server-side links -- needs its JSON API"
    else:
        res.outcome = "DEAD"
        res.detail = f"no repeating catalogue ({links} deep links, {imgs} images)"


def _probe_madara(res: CandidateResult, fetcher: _Fetcher, host: str, home_html: str) -> None:
    """Fill in the four fields a ``catalog.py`` line needs, or reject the site."""
    segment, _n = _guess_segment(home_html, host)
    listing_html = ""
    if segment:
        status, listing_html, _h, _e = fetcher.get(f"https://{host}/{segment}/", use_cf=res.needs_cf)
        if status != 200 or "page-item-detail" not in listing_html.lower():
            listing_html = ""
    if not listing_html:
        tried = [segment] if segment else []
        for seg in CANDIDATE_SEGMENTS:
            if seg in tried or len(tried) >= 4 or fetcher.expired():
                continue
            tried.append(seg)
            status, body, _h, _e = fetcher.get(f"https://{host}/{seg}/", use_cf=res.needs_cf)
            if status == 200 and "page-item-detail" in body.lower():
                segment, listing_html = seg, body
                break
    if not listing_html:
        # Some installs only expose the archive through the post_type query.
        status, body, _h, _e = fetcher.get(
            f"https://{host}/?post_type=wp-manga", use_cf=res.needs_cf
        )
        if status == 200 and "page-item-detail" in body.lower():
            listing_html = body
            res.listing_post_type = "wp-manga"
            segment = segment or _guess_segment(body, host)[0] or "manga"

    if not listing_html:
        res.outcome = "DEAD"
        res.cms = "madara"
        res.detail = "Madara markup but no enumerable listing"
        return

    res.url_segment = segment
    series = _series_links(listing_html, host, segment)
    res.listing_cards = listing_html.lower().count("page-item-detail")
    res.real_catalogue = res.listing_cards >= 3 and bool(series)
    if not res.real_catalogue:
        res.outcome = "DEAD"
        res.detail = f"listing has {res.listing_cards} cards, {len(series)} series links"
        return

    hosts: list[str] = []
    cover_hosts, _n = _img_hosts(listing_html, host)
    hosts.extend(h for h in cover_hosts if h not in hosts)

    if series and not fetcher.expired():
        status, detail_html, _h, _e = fetcher.get(series[0], use_cf=res.needs_cf)
        if status == 200 and detail_html:
            low = detail_html.lower()
            if "/ajax/chapters" in low:
                res.chapter_mechanism = "series-relative ajax/chapters"
            elif "wp-manga-chapter" in low:
                res.chapter_mechanism = "inline wp-manga-chapter list"
            elif "admin-ajax.php" in low:
                res.chapter_mechanism = "admin-ajax manga_get_chapters"
            chapter = re.search(
                rf"https?://(?:www\.)?{re.escape(host)}/{re.escape(segment)}/[a-z0-9%_-]+/[a-z0-9%_.-]*chapter[a-z0-9%_.-]*/?",
                detail_html,
                re.I,
            )
            if chapter and not fetcher.expired():
                st, chap_html, _hh, _ee = fetcher.get(chapter.group(0), use_cf=res.needs_cf)
                if st == 200 and chap_html:
                    reading = re.search(
                        r'class="[^"]*reading-content[^"]*"(.*?)(?:</div>\s*</div>|$)',
                        chap_html, re.I | re.S,
                    )
                    page_hosts, page_count = _img_hosts(reading.group(1) if reading else chap_html, host)
                    res.page_images = page_count
                    hosts.extend(h for h in page_hosts if h not in hosts)

    res.image_hosts = [h for h in hosts if h and h != host and h != f"www.{host}"][:6]
    res.outcome = "MADARA"


def _run_candidates(entries: list[dict], workers: int) -> list[CandidateResult]:
    registered = _registered_hosts()
    results: list[CandidateResult] = []
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_probe_candidate, e, registered): e["domain"] for e in entries}
        for future in as_completed(futures):
            done += 1
            try:
                result = future.result()
            except Exception as exc:  # a probe must never take the batch with it
                result = CandidateResult(
                    domain=futures[future], name="", kind="", claimed_mature=False,
                    suspected_cms="", outcome="ERROR", detail=f"{type(exc).__name__}: {exc}"[:180],
                )
            results.append(result)
            extra = f"seg={result.url_segment} " if result.url_segment else ""
            print(
                f"[{done}/{len(entries)}] {result.outcome:12} {result.domain:34} "
                f"cms={result.cms:10} cards={result.listing_cards:<4} {extra}{result.detail[:44]}",
                flush=True,
            )
    return results


def _candidate_main(args) -> None:
    entries = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    if args.offset or args.limit:
        entries = entries[args.offset: args.offset + args.limit if args.limit else None]
    print(f"Probing {len(entries)} candidate domains (offset {args.offset})...", flush=True)
    results = _run_candidates(entries, args.workers)
    counts: dict[str, int] = {}
    for r in results:
        counts[r.outcome] = counts.get(r.outcome, 0) + 1
    payload = {
        "probed_at": datetime.now(UTC).isoformat(),
        "probed_from": os.environ.get("MM_PROBE_FROM", "local"),
        "total": len(results),
        "counts": counts,
        "results": [asdict(r) for r in sorted(results, key=lambda r: (r.outcome, r.domain))],
    }
    out = Path(args.out) if args.out else CANDIDATE_RESULTS
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("\n=== BATCH SUMMARY ===", flush=True)
    for label, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {label}: {count}", flush=True)
    print(f"Written: {out}", flush=True)


def _run_candidates_remote(args) -> int:
    """Drive the probe inside the production container, one bounded batch per ssh.

    Residential egress sails past walls that reject the OVH address, so a
    local answer here is worse than none. Batching from this side keeps every
    remote command finite and prints as it goes -- a single ssh spanning 230
    domains is exactly the shape that hung an earlier run.
    """
    token = f"{os.getpid()}_{int(time.time() * 1000) % 1_000_000}"
    script = Path(__file__).resolve()
    host_script = f"/tmp/probe_cand_{token}.py"
    host_cands = f"/tmp/probe_cand_{token}.json"
    entries = json.loads(Path(args.candidates).read_text(encoding="utf-8"))

    subprocess.run(["scp", "-o", "BatchMode=yes", str(script), f"{VPS_HOST}:{host_script}"], check=True)
    subprocess.run(
        ["scp", "-o", "BatchMode=yes", str(Path(args.candidates)), f"{VPS_HOST}:{host_cands}"],
        check=True,
    )
    subprocess.run(
        ["ssh", "-o", "BatchMode=yes", VPS_HOST,
         f"docker exec {VPS_CONTAINER} mkdir -p /app/scripts && "
         f"docker cp {host_script} {VPS_CONTAINER}:/app/scripts/_cand_{token}.py && "
         f"docker cp {host_cands} {VPS_CONTAINER}:/tmp/cand_{token}.json"],
        check=True,
    )

    merged: list[dict] = []
    batch = args.batch_size
    rc = 0
    for offset in range(args.offset, len(entries), batch):
        size = min(batch, len(entries) - offset)
        ctr_out = f"/tmp/cand_out_{token}_{offset}.json"
        print(f"\n===== batch {offset}-{offset + size - 1} of {len(entries)} =====", flush=True)
        cmd = (
            f"docker exec -w /app -e MM_PROBE_FROM=vps {VPS_CONTAINER} "
            f"python /app/scripts/_cand_{token}.py --candidates /tmp/cand_{token}.json "
            f"--offset {offset} --limit {size} --workers {args.workers} --out {ctr_out}"
        )
        proc = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", VPS_HOST, cmd],
            timeout=args.batch_timeout,
        )
        if proc.returncode != 0:
            rc = proc.returncode
            print(f"!! batch {offset} exited {proc.returncode}", flush=True)
            continue
        local_tmp = f"/tmp/cand_out_{token}_{offset}.json"
        subprocess.run(
            ["ssh", "-o", "BatchMode=yes", VPS_HOST,
             f"docker cp {VPS_CONTAINER}:{ctr_out} {local_tmp} && "
             f"docker exec {VPS_CONTAINER} rm -f {ctr_out}"],
            check=False,
        )
        fetched = subprocess.run(
            ["scp", "-o", "BatchMode=yes", f"{VPS_HOST}:{local_tmp}", local_tmp]
        )
        subprocess.run(["ssh", "-o", "BatchMode=yes", VPS_HOST, f"rm -f {local_tmp}"], check=False)
        if fetched.returncode == 0:
            merged.extend(json.loads(Path(local_tmp).read_text(encoding="utf-8"))["results"])

    subprocess.run(
        ["ssh", "-o", "BatchMode=yes", VPS_HOST,
         f"docker exec {VPS_CONTAINER} rm -f /app/scripts/_cand_{token}.py /tmp/cand_{token}.json; "
         f"rm -f {host_script} {host_cands}"],
        check=False,
    )

    counts: dict[str, int] = {}
    for row in merged:
        counts[row["outcome"]] = counts.get(row["outcome"], 0) + 1
    out = Path(args.out) if args.out else CANDIDATE_RESULTS
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "probed_at": datetime.now(UTC).isoformat(),
                "probed_from": "vps:135.148.43.147 (manhwamaniacs-backend)",
                "total": len(merged),
                "counts": counts,
                "results": sorted(merged, key=lambda r: (r["outcome"], r["domain"])),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("\n=== RUN SUMMARY ===", flush=True)
    for label, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {label}: {count}", flush=True)
    print(f"Written: {out}", flush=True)
    return rc


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Probe catalog domains for structure")
    parser.add_argument(
        "--ids",
        nargs="*",
        help="Probe only these source_ids (default: full Madara catalog)",
    )
    parser.add_argument(
        "--retry-dead",
        action="store_true",
        help="Only re-probe sources classified DEAD/UNREACHABLE last run",
    )
    parser.add_argument(
        "--candidates",
        help="JSON list of unregistered {domain,name,kind,mature,suspected_cms} "
             "entries to classify instead of the catalog",
    )
    parser.add_argument("--out", help="write results here (candidate mode)")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=MAX_WORKERS)
    parser.add_argument(
        "--remote",
        action="store_true",
        help="with --candidates: probe from the production container over ssh",
    )
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--batch-timeout", type=float, default=900.0)
    args = parser.parse_args()

    if args.candidates:
        if args.remote:
            raise SystemExit(_run_candidates_remote(args))
        _candidate_main(args)
        return

    strikes = _load_strikes()
    configs = list(MADARA_CATALOG)

    if args.ids:
        wanted = set(args.ids)
        configs = [c for c in configs if c.source_id in wanted]
    elif args.retry_dead and RESULTS_PATH.exists():
        prev = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        dead_ids = {
            r["source_id"]
            for r in prev["results"]
            if r["classification"] in ("DEAD", "UNREACHABLE")
        }
        configs = [c for c in configs if c.source_id in dead_ids]

    print(f"Domain-probing {len(configs)} catalog entries...", flush=True)

    results: list[DomainProbeResult] = []
    done = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(
                _probe_site,
                cfg.source_id,
                cfg.site_host,
                mature=cfg.mature,
                url_segment=cfg.url_segment,
                use_cf=cfg.use_cf,
                strikes=strikes,
            ): cfg.source_id
            for cfg in configs
        }
        for future in as_completed(futures):
            sid = futures[future]
            done += 1
            result = future.result()
            results.append(result)
            print(
                f"[{done}/{len(configs)}] {result.classification:14} {sid:22} "
                f"cards={result.listing_cards} {result.detail[:40]}",
                flush=True,
            )

    # Include handcrafted rows for a complete status table
    for sid in sorted(HANDCRAFTED):
        if not any(r.source_id == sid for r in results):
            results.append(
                DomainProbeResult(
                    source_id=sid,
                    domain="(custom)",
                    mature=sid in MATURE_SOURCE_IDS,
                    url_segment="n/a",
                    classification="HANDCRAFTED",
                    detail="registered custom connector",
                )
            )

    results.sort(key=lambda r: (r.classification, r.source_id))

    counts: dict[str, int] = {}
    for r in results:
        counts[r.classification] = counts.get(r.classification, 0) + 1

    payload = {
        "probed_at": datetime.now(UTC).isoformat(),
        "total": len(results),
        "counts": counts,
        "three_strike_dead": [
            r.source_id for r in results if r.strikes >= 3 and r.classification in ("DEAD", "UNREACHABLE")
        ],
        "results": [asdict(r) for r in results],
    }

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("\n=== DOMAIN PROBE SUMMARY ===")
    for label, count in sorted(counts.items()):
        print(f"  {label}: {count}")
    print(f"  3-strike skip list: {len(payload['three_strike_dead'])}")
    print(f"Written: {RESULTS_PATH}")


if __name__ == "__main__":
    main()
