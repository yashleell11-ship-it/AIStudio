"""Browse online sources through connector implementations."""

from __future__ import annotations

import asyncio
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from itertools import zip_longest
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends
from sqlalchemy.orm import Session

from core.config import get_settings
from core.content_rating import resolve_mature_gate
from core.errors import AppError
from core.profile_context import ProfileContext, resolve_profile_context
from database.session import get_db
from connectors.base import SourceConnector
from connectors.http.client import ConnectorHttpError
from connectors.ids import fully_unquote
from connectors.models import Chapter, Page, PaginatedSeriesList, Series
from connectors.registry import (
    ConnectorDescriptor,
    create_connector,
    list_installed_connectors,
    registry_snapshot,
)
from services.nas_listing import PAGE_SIZE as NAS_PAGE_SIZE
from services.nas_listing import nas_listing
from services.outbound_security import validate_outbound_url
from services.source_health import (
    SourceHealthState,
    load_states,
    record_outcomes,
    states_for,
    summarize,
)

logger = logging.getLogger(__name__)

# Federated search fan-out tuning. The fan-out is I/O bound across dozens of
# unrelated sites, so it gets a dedicated pool instead of the shared default
# executor: the previous semaphore of 8 serialised the registry into
# ceil(N/8) rounds of _SEARCH_TIMEOUT_SECONDS, measured at 34-52s against the
# mobile client's 30s receive timeout (i.e. search failed outright). Fanning
# out to every source at once measured 10.8s on the same 50-source registry.
_SEARCH_MAX_WORKERS = 128
_SEARCH_TIMEOUT_SECONDS = 8.0
# Whole-request budget. Whatever has not resolved by the deadline is reported
# as a failed source so the client always gets its page back in time.
_SEARCH_DEADLINE_SECONDS = 12.0
# Search runs on a much tighter HTTP budget than browsing (30s x 3 retries):
# one wedged site must not eat the deadline. Applied only to the search-scoped
# connector instances built by _search_connector, so browsing keeps its
# resilience.
_SEARCH_HTTP_TIMEOUT_SECONDS = 6.0
_SEARCH_HTTP_RETRIES = 1
# A source that answers with this many titles, none of which share a token with
# the query, is answering something other than what was asked -- baozimh returns
# its whole 82-title catalog for every query -- so its results are dropped.
# Below the threshold results are only demoted, never dropped: a narrow result
# set with no literal overlap is exactly how a genuine alternative-title hit
# looks (MangaDex answers "lookism" with the single romanized title
# "Oemo Jisangjuui").
_QUERY_IGNORED_MIN_ITEMS = 10
_WHITESPACE_RE = re.compile(r"\s+")
_TOKEN_SPLIT_RE = re.compile(r"[^\w]+", re.UNICODE)
_LOCAL_GROUP_NAME = "My Library"

_search_executor: ThreadPoolExecutor | None = None
_search_executor_lock = threading.Lock()
# Search-scoped connector instances, one per source (see _search_connector).
_search_connectors: dict[str, SourceConnector] = {}
_search_connectors_lock = threading.Lock()


def _absolute_url(base_url: str, path: str) -> str:
    """Join a request base URL (``http://host/``) with a relative API path."""
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _normalize_title(title: str) -> str:
    """Collapse whitespace + casefold for duplicate detection within a source."""
    return _WHITESPACE_RE.sub(" ", (title or "").strip()).casefold()


def _query_tokens(query: str) -> list[str]:
    return [token for token in _TOKEN_SPLIT_RE.split(query.casefold()) if token]


def _relevance_score(title: str, query_norm: str, tokens: list[str]) -> float:
    """Rank one result title against the query. ``0.0`` means "shares nothing".

    Only the title is available here -- connectors normalize away the alternative
    titles a site matched on -- so a zero score means "no literal overlap", not
    "wrong result". Callers demote zeros rather than discarding them; see
    _QUERY_IGNORED_MIN_ITEMS for the one case where a source is dropped.
    """
    normalized = _normalize_title(title)
    if not normalized or not tokens:
        return 0.0
    if normalized == query_norm:
        return 4.0
    if query_norm in normalized:
        return 3.0
    matched = sum(1 for token in tokens if token in normalized)
    if matched == len(tokens):
        return 2.0
    if matched:
        return 1.0 + matched / len(tokens)
    return 0.0


_URL_IN_TEXT = re.compile(r"https?://\S+")


def _redact_urls(text: str) -> str:
    """Strip URLs out of an error string.

    httpx builds its message from the failing request URL, which for a search
    carries the query string. This message is persisted on the GLOBAL
    source_health row and served to every authenticated caller, so leaving it
    intact made one account's search terms readable by another. The rest of the
    message is genuinely useful when diagnosing a dead source, so redact rather
    than discard.
    """
    return _URL_IN_TEXT.sub("<url>", text).strip()


def _search_error_message(exc: BaseException) -> str:
    """One-line, client-safe reason a source contributed nothing."""
    if isinstance(exc, TimeoutError):
        return "Timed out."
    if isinstance(exc, ConnectorHttpError) and exc.status_code == 403:
        return "Access blocked (403). This source may use Cloudflare or bot protection."
    return _redact_urls(str(exc)) or exc.__class__.__name__


def _get_search_executor() -> ThreadPoolExecutor:
    """The federated fan-out's own thread pool.

    Sized to hold the whole registry at once; threads are spawned on demand, so
    a small search costs no more than a small pool. Kept off the default
    executor so a wedged source cannot starve unrelated background work.
    """
    global _search_executor
    if _search_executor is None:
        with _search_executor_lock:
            if _search_executor is None:
                _search_executor = ThreadPoolExecutor(
                    max_workers=_SEARCH_MAX_WORKERS,
                    thread_name_prefix="federated-search",
                )
    return _search_executor


def _apply_search_http_budget(connector: SourceConnector) -> None:
    """Tighten every HTTP client the connector owns to the search budget.

    Both connector HTTP clients (httpx and the curl_cffi one) expose the same
    ``_timeout`` / ``_max_retries`` knobs. Reaching for them here keeps the
    budget in one place instead of threading a parameter through 50 connector
    files, and it is only ever applied to the search-scoped instance below --
    never to the shared instance browsing uses.
    """
    for value in vars(connector).values():
        timeout = getattr(value, "_timeout", None)
        retries = getattr(value, "_max_retries", None)
        if not isinstance(timeout, (int, float)) or not isinstance(retries, int):
            continue
        value._timeout = min(float(timeout), _SEARCH_HTTP_TIMEOUT_SECONDS)
        value._max_retries = min(retries, _SEARCH_HTTP_RETRIES)
        # httpx.Client keeps its own copy of the timeout for every request.
        inner = getattr(value, "_client", None)
        if inner is not None and hasattr(inner, "timeout"):
            inner.timeout = _SEARCH_HTTP_TIMEOUT_SECONDS


def _search_connector(source_id: str) -> SourceConnector:
    """Return the connector instance the federated fan-out should use.

    The registry hands browsing a cached instance per source; search needs a
    tighter HTTP budget than browsing, so it keeps its own instance rather than
    mutating a shared one out from under a concurrent browse request.
    """
    connector = create_connector(source_id)
    if not isinstance(connector, SourceConnector):
        # Test doubles and anything else non-standard are used untouched.
        return connector
    cached = _search_connectors.get(source_id)
    if cached is not None and type(cached) is type(connector):
        return cached
    try:
        scoped = type(connector)()
    except Exception:  # pragma: no cover - connector needs constructor config
        logger.debug("federated_search source=%s has no search-scoped instance", source_id)
        return connector
    _apply_search_http_budget(scoped)
    with _search_connectors_lock:
        return _search_connectors.setdefault(source_id, scoped)


def _round_robin(buckets: list[list[dict[str, object]]], limit: int) -> list[dict[str, object]]:
    """Interleave per-source result lists, one item per source per round.

    This replaces the flat ``merged[:per_page]`` truncation: with sources
    concatenated in connector display-name order, the third source alone
    (baozimh, 82 catalog titles) consumed all 40 slots and the real hits never
    reached the page.
    """
    picked: list[dict[str, object]] = []
    for row in zip_longest(*buckets):
        for item in row:
            if item is None:
                continue
            picked.append(item)
            if len(picked) >= limit:
                return picked
    return picked


def _normalize_source_chapter_id(chapter_id: str) -> str:
    """Decode chapter IDs from URL paths (may contain ``/`` for some sources)."""
    return fully_unquote(chapter_id).strip().strip("/")


def _serialize_series(series: Series, source_id: str) -> dict[str, object]:
    return {
        "id": series.id,
        "source_id": source_id,
        "title": series.title,
        "chapter_count": series.chapter_count,
        "description": series.description,
        "author": series.author,
        "artist": series.artist,
        "status": series.status,
        "genres": list(series.genres),
        "latest_chapter": series.latest_chapter,
        "cover_url": f"/sources/{source_id}/series/{quote(series.id, safe='')}/cover",
    }


def _serialize_chapter(chapter: Chapter, source_id: str) -> dict[str, object]:
    return {
        "id": chapter.id,
        "source_id": source_id,
        "series_id": chapter.series_id,
        "title": chapter.title,
        "number": chapter.number,
        "page_count": chapter.page_count,
        "release_date": chapter.release_date,
    }


def _serialize_page(page: Page, source_id: str) -> dict[str, object]:
    return {
        "id": page.id,
        "chapter_id": page.chapter_id,
        "number": page.number,
        "width": page.width,
        "height": page.height,
        "image_url": f"/sources/{source_id}/pages/{quote(page.id, safe='')}/image",
    }


def _invalidate_series_caches(connector: SourceConnector, series_id: str) -> None:
    """Drop per-series connector caches after a transient upstream miss."""
    api_key = fully_unquote(series_id).strip().strip("/")
    if api_key.startswith("serie/"):
        api_key = api_key.removeprefix("serie/")
    for cache_name in ("_series_cache", "_chapter_list_cache", "_gallery_cache", "_page_cache"):
        cache = getattr(connector, cache_name, None)
        if cache is not None and hasattr(cache, "pop"):
            cache.pop(api_key)


def _serialize_paginated(
    listing: PaginatedSeriesList,
    source_id: str,
) -> dict[str, object]:
    from utils.api_pagination import enrich_pagination_aliases

    return enrich_pagination_aliases(
        {
            "items": [_serialize_series(item, source_id) for item in listing.items],
            "page": listing.page,
            "page_size": listing.page_size,
            "total": listing.total,
            "total_pages": listing.total_pages,
            "has_more": listing.has_more,
        }
    )


#: Sort id for the NAS view. Not a value any connector emits, so it can never
#: collide with a source's own catalog mode.
NAS_MODE = "nas"


class BrowseService:
    """Source-agnostic facade for browsing online catalogs."""

    def __init__(
        self,
        mature_enabled: bool | None = None,
        db: Session | None = None,
        user_id: int | None = None,
        profile_id: int | None = None,
    ) -> None:
        """``mature_enabled`` is the caller's *resolved* 18+ gate.

        It is passed in rather than looked up because the gate is per-(user,
        profile) and this service holds neither a DB session nor a
        ``ProfileContext`` -- reading ``get_settings()`` here is exactly the bug
        that made the in-app toggle inert. ``get_browse_service`` resolves it
        from the request's profile.

        ``None`` means "no caller context", and falls back to the global config
        default at *call* time (not construction, so a settings change is
        observed). That path exists only for the handful of context-free
        callers: the federated search fan-out, cover prefetching for series
        already in a library, and direct construction in connector tests.

        ``db`` is the caller's request-scoped session, used ONLY for source
        health (reading it, and recording what the search fan-out observed).
        It is optional for the same reason as the gate: the context-free
        callers above have no session, and a service without one simply reports
        every source's health as unknown instead of failing.

        ``user_id``/``profile_id`` scope the NAS browse mode. Downloads belong
        to a (user, profile) pair exactly like library membership does, so
        without them the NAS listing would show one reader what another reader
        downloaded. Absent context yields an empty NAS listing rather than an
        unscoped one -- the safe direction to fail.
        """
        self._mature_enabled = mature_enabled
        self._db = db
        self._user_id = user_id
        self._profile_id = profile_id

    def _gate_open(self) -> bool:
        """Whether adult content is permitted for whoever built this service."""
        if self._mature_enabled is not None:
            return self._mature_enabled
        return get_settings().mature_content_enabled

    @staticmethod
    def _raise_source_connector_error(source_id: str, exc: Exception) -> None:
        """Map upstream connector failures to client-facing browse errors."""
        if isinstance(exc, ConnectorHttpError):
            if exc.status_code == 403:
                message = (
                    "Access blocked (403). This source may use Cloudflare or bot protection."
                )
            else:
                message = str(exc) or "Could not load source catalog."
            raise AppError(
                message,
                code="source_unreachable",
                status_code=502,
                details={"source_id": source_id},
            ) from exc
        if isinstance(exc, OSError):
            raise AppError(
                "Could not reach the source site (network timeout).",
                code="source_unreachable",
                status_code=502,
                details={"source_id": source_id},
            ) from exc
        raise exc

    def _visible_descriptors(self) -> list[ConnectorDescriptor]:
        """The browsable sources this caller's 18+ gate allows.

        Single definition of "sources I can see", so the health surfaces below
        cannot drift from what ``list_sources`` shows.
        """
        return list_installed_connectors(
            browsable_only=True,
            include_mature=self._gate_open(),
        )

    def _health_for(
        self, descriptors: list[ConnectorDescriptor]
    ) -> dict[str, SourceHealthState]:
        """Health keyed by source id, for these descriptors only.

        Health is stored globally but read through the caller's own gated
        descriptor list, so a mature source's health cannot reach a profile
        that is not allowed to know the source exists.
        """
        return states_for(
            load_states(self._db), [descriptor.source_type for descriptor in descriptors]
        )

    @staticmethod
    def _source_payload(
        descriptor: ConnectorDescriptor, health: SourceHealthState
    ) -> dict[str, object]:
        """One row of the source listing. Shared by /sources and /sources/health
        so the two can never disagree about a source's shape."""
        return {
            "id": descriptor.source_type,
            "source_id": descriptor.source_type,
            "name": descriptor.name,
            "description": descriptor.description,
            "browsable": descriptor.browsable,
            "supports_import": descriptor.supports_import,
            # Carried through so the client can badge 18+ sources; the
            # descriptor has always had it, the payload just dropped it.
            "mature": descriptor.mature,
            "icon_url": descriptor.icon_url,
            # Additive: lets the listing badge a source the owner's searches
            # have found unreachable, instead of it looking installed and fine
            # right up until a followed series stops updating.
            "health": health.payload(),
        }

    def list_sources(self) -> list[dict[str, object]]:
        snapshot = registry_snapshot()
        descriptors = self._visible_descriptors()
        health = self._health_for(descriptors)
        logging.getLogger("uvicorn.error").info(
            "GET /sources registry_id=%s all_types=%s browsable_types=%s returning=%s",
            snapshot["registry_id"],
            snapshot["connector_types"],
            snapshot["browsable_types"],
            [descriptor.source_type for descriptor in descriptors],
        )
        return [
            self._source_payload(descriptor, health[descriptor.source_type])
            for descriptor in descriptors
        ]

    def list_source_health(self) -> list[dict[str, object]]:
        """The same rows as ``list_sources``, ordered worst-first.

        Deliberately not a different payload shape, so a client can render
        either list with one component; the only difference is the order --
        dead sources first, then failing, then never-probed, then healthy --
        because the question this view answers is "what is broken", not "what
        can I browse". A failing source is never omitted: hiding it is exactly
        how the owner ended up unable to tell a dead source from a quiet one.
        """
        descriptors = self._visible_descriptors()
        health = self._health_for(descriptors)
        ordered = sorted(
            descriptors,
            key=lambda descriptor: (
                health[descriptor.source_type].severity,
                -health[descriptor.source_type].consecutive_failures,
                descriptor.name.casefold(),
            ),
        )
        return [
            self._source_payload(descriptor, health[descriptor.source_type])
            for descriptor in ordered
        ]

    def source_health_summary(self) -> dict[str, int]:
        """Counts by status across the sources this caller can see."""
        return summarize(self._health_for(self._visible_descriptors()).values())

    def _get_connector(self, source_id: str) -> SourceConnector:
        try:
            connector = create_connector(source_id)
        except ValueError as exc:
            raise AppError(
                "Source not found.",
                code="source_not_found",
                status_code=404,
                details={"source_id": source_id},
            ) from exc
        if not connector.is_browsable:
            raise AppError(
                "Source is not browsable.",
                code="source_not_browsable",
                status_code=400,
                details={"source_id": source_id},
            )
        # A mature source is hidden entirely when the user has not opted into
        # adult content: report it as not-found rather than "forbidden" so its
        # existence isn't disclosed. This one check covers every read path
        # (browse, search, series, chapters, pages, reader, covers) because
        # they all resolve their connector here.
        if connector.is_mature and not self._gate_open():
            raise AppError(
                "Source not found.",
                code="source_not_found",
                status_code=404,
                details={"source_id": source_id},
            )
        return connector

    def list_browse_modes(self, source_id: str) -> list[dict[str, str]]:
        connector = self._get_connector(source_id)
        modes = [
            {"id": mode.id, "label": mode.label} for mode in connector.list_browse_modes()
        ]
        # Injected here rather than declared on each connector: NAS is not a
        # catalog the source offers, it is a view of what this server already
        # holds from it. Every one of the ~50 connectors gets it for free, and
        # none of them can forget to.
        modes.append({"id": NAS_MODE, "label": "NAS"})
        return modes

    def list_genres(self, source_id: str) -> list[dict[str, str]]:
        connector = self._get_connector(source_id)
        return [{"id": mode.id, "label": mode.label} for mode in connector.list_genres()]

    def list_series(
        self,
        source_id: str,
        *,
        page: int = 1,
        query: str | None = None,
        sort: str | None = None,
        genre: str | None = None,
    ) -> dict[str, object]:
        connector = self._get_connector(source_id)
        normalized_query = query.strip() if query else None
        normalized_sort = sort.strip() if sort else None
        normalized_genre = genre.strip() if genre else None
        if normalized_sort == "default":
            normalized_sort = None

        # NAS is answered from this server's own downloads, so it returns
        # before any connector call. _get_connector still runs above: an
        # unknown or gated source must 404 the same way it does for every
        # other mode, rather than quietly serving a local listing for a source
        # this caller is not allowed to see.
        if normalized_sort == NAS_MODE:
            if self._db is None:
                listing = PaginatedSeriesList(page=page, page_size=NAS_PAGE_SIZE)
            else:
                listing = nas_listing(
                    self._db,
                    source_id=source_id,
                    user_id=self._user_id,
                    profile_id=self._profile_id,
                    page=page,
                    query=normalized_query,
                )
            return _serialize_paginated(listing, source_id)

        try:
            if normalized_genre and normalized_query:
                listing = connector.search_series(
                    f"{normalized_genre} {normalized_query}",
                    page,
                    sort=normalized_sort,
                )
                operation = "genre_search"
            elif normalized_genre:
                try:
                    listing = connector.browse_by_genre(
                        normalized_genre,
                        page,
                        sort=normalized_sort,
                    )
                    operation = "genre_browse"
                except NotImplementedError:
                    listing = connector.search_series(
                        normalized_genre, page, sort=normalized_sort
                    )
                    operation = "genre_search"
            elif normalized_query:
                listing = connector.search_series(normalized_query, page, sort=normalized_sort)
                operation = "search"
            else:
                listing = connector.get_series_list(page, sort=normalized_sort)
                operation = "browse"
        except (ConnectorHttpError, OSError) as exc:
            self._raise_source_connector_error(source_id, exc)

        logger.info(
            "%s source=%s page=%d sort=%r query=%r genre=%r parsed=%d total=%d total_pages=%d has_more=%s",
            operation,
            source_id,
            page,
            normalized_sort,
            normalized_query,
            normalized_genre,
            len(listing.items),
            listing.total,
            listing.total_pages,
            listing.has_more,
        )
        return _serialize_paginated(listing, source_id)

    async def _fan_out_search(
        self,
        query: str,
        source_ids: list[str],
        *,
        page: int,
    ) -> dict[str, PaginatedSeriesList | BaseException]:
        """Query every source at once, bounded per source and overall.

        Returns one entry per source: its listing, or the exception explaining
        why it contributed nothing. Sources still running at the overall
        deadline are cancelled and reported as timed out -- their threads are
        left to drain in the dedicated pool rather than holding up the response.
        """
        loop = asyncio.get_running_loop()
        executor = _get_search_executor()

        async def _search_one(source_id: str) -> PaginatedSeriesList:
            def _work() -> PaginatedSeriesList:
                return _search_connector(source_id).search_series(query, page, sort=None)

            return await asyncio.wait_for(
                loop.run_in_executor(executor, _work),
                timeout=_SEARCH_TIMEOUT_SECONDS,
            )

        tasks = {
            asyncio.ensure_future(_search_one(source_id)): source_id
            for source_id in source_ids
        }
        done, pending = await asyncio.wait(tasks, timeout=_SEARCH_DEADLINE_SECONDS)

        outcomes: dict[str, PaginatedSeriesList | BaseException] = {}
        for task in done:
            failure = task.exception()
            outcomes[tasks[task]] = failure if failure is not None else task.result()
        for task in pending:
            task.cancel()
            outcomes[tasks[task]] = TimeoutError("Search deadline exceeded.")
        return outcomes

    def _merge_health(
        self, outcomes: dict[str, PaginatedSeriesList | BaseException]
    ) -> dict[str, SourceHealthState]:
        """Record this fan-out's outcomes and return health for every source.

        Sources that were not probed (empty query) keep whatever was already
        recorded -- nothing was learned about them, so nothing is written.

        A source counts as OK whenever it *answered*, including with zero
        results or with the unrelated-catalog dump that
        ``_QUERY_IGNORED_MIN_ITEMS`` throws away. That is deliberate: those are
        relevance problems, and treating them as outages would demote a
        perfectly reachable source and make the health table lie about why the
        results are bad.
        """
        stored = load_states(self._db)
        if not outcomes:
            return stored
        results = {
            source_id: (
                _search_error_message(outcome)
                if isinstance(outcome, BaseException)
                else None
            )
            for source_id, outcome in outcomes.items()
        }
        try:
            return {**stored, **record_outcomes(self._db, results)}
        except Exception:  # pragma: no cover - defensive
            # Health is diagnostic metadata about the search; it must never be
            # the reason the search itself fails. record_outcomes already
            # handles database errors, so reaching here means a bug -- log it
            # loudly and serve the results with the last known health.
            logger.exception("federated_search could not record source health")
            return stored

    def _build_source_group(
        self,
        descriptor: ConnectorDescriptor,
        outcome: PaginatedSeriesList | BaseException | None,
        *,
        base_url: str,
        query_norm: str,
        tokens: list[str],
        health: SourceHealthState,
    ) -> tuple[dict[str, object], float]:
        """Turn one source's outcome into a display group + its best score."""
        source_id = descriptor.source_type
        group: dict[str, object] = {
            "source": source_id,
            "source_name": descriptor.name,
            "icon_url": descriptor.icon_url,
            "status": "empty",
            "error": None,
            "total": 0,
            "has_more": False,
            "items": [],
            # Recorded reachability, so the screen can label a source that has
            # been failing for weeks differently from one that failed just now.
            "health": health.payload(),
        }
        if outcome is None:
            return group, 0.0
        if isinstance(outcome, BaseException):
            group["status"] = "error"
            group["error"] = _search_error_message(outcome)
            logger.warning(
                "federated_search source=%s query=%r failed: %r", source_id, query_norm, outcome
            )
            return group, 0.0

        scored: list[tuple[float, dict[str, object]]] = []
        seen: set[str] = set()
        for series in outcome.items:
            # De-dupe WITHIN one source only. The same series legitimately shows
            # up under several sources and each keeps its own row: collapsing
            # across sources is what reduced the five real Lookism hits to one.
            key = _normalize_title(series.title)
            if key in seen:
                continue
            seen.add(key)
            scored.append(
                (
                    _relevance_score(series.title, query_norm, tokens),
                    {
                        "kind": "source",
                        "source": source_id,
                        "series_id": str(series.id),
                        "title": series.title,
                        "cover_url": _absolute_url(
                            base_url,
                            f"/sources/{source_id}/series/"
                            f"{quote(str(series.id), safe='')}/cover",
                        ),
                        "author": series.author,
                        # Carried through so source-migration candidates can be
                        # compared on catalog size without an extra fetch per
                        # candidate. 0 means "the source did not say", not
                        # "empty" -- most search endpoints omit it.
                        "chapter_count": series.chapter_count,
                        "extra": None,
                    },
                )
            )

        best_score = max((score for score, _ in scored), default=0.0)
        if best_score <= 0.0 and len(scored) >= _QUERY_IGNORED_MIN_ITEMS:
            group["error"] = (
                f"Source returned {len(scored)} results unrelated to the query; ignored."
            )
            logger.info(
                "federated_search source=%s query=%r ignored the query (%d unrelated titles)",
                source_id,
                query_norm,
                len(scored),
            )
            return group, 0.0

        # Stable sort: best matches first, source order preserved within a tier.
        scored.sort(key=lambda pair: -pair[0])
        items = [item for _, item in scored]
        group["items"] = items
        group["total"] = len(items)
        group["has_more"] = bool(outcome.has_more)
        group["status"] = "ok" if items else "empty"
        return group, best_score

    async def federated_search(
        self,
        query: str,
        *,
        page: int = 1,
        per_page: int = 40,
        include_mature: bool = False,
        local_items: list[dict[str, object]] | None = None,
        local_has_more: bool = False,
        base_url: str = "",
    ) -> dict[str, object]:
        """Search the local library AND every browsable source in parallel.

        ``local_items`` are already-serialized ``kind:"local"`` hits (the caller
        owns the DB session, so it queries the library and passes them in).
        ``local_has_more`` reports whether the library query itself has further
        pages, so a local-only result set is not falsely truncated to one page.

        Results are returned twice: as ``groups`` (the library plus one group
        per source, which is what the screen renders) and as the flat ``items``
        list older clients still read. ``items`` interleaves the groups instead
        of truncating a concatenation, so no single source can consume the page.
        """
        local_items = list(local_items or [])
        normalized_query = query.strip()

        # Resolve the browsable sources the same way ``list_sources`` does,
        # honouring the caller's mature-content gate (adult sources dropped off).
        # NOTE: this path takes the gate as an argument rather than reading
        # ``self._gate_open()``, so it cannot use ``_visible_descriptors``.
        descriptors = list_installed_connectors(
            browsable_only=True,
            include_mature=include_mature,
        )
        sources_queried = len(descriptors)

        outcomes: dict[str, PaginatedSeriesList | BaseException] = {}
        if normalized_query and descriptors:
            outcomes = await self._fan_out_search(
                normalized_query,
                [descriptor.source_type for descriptor in descriptors],
                page=page,
            )

        # The fan-out already probed every source and caught every failure, so
        # it is the one place that knows whether a source is answering without
        # spending a single extra request. Recording happens BEFORE the groups
        # are built so this response reflects what it just observed -- in
        # particular, a source that recovered is un-demoted by the very search
        # that found it working.
        health = states_for(
            self._merge_health(outcomes), [d.source_type for d in descriptors]
        )

        query_norm = _normalize_title(normalized_query)
        tokens = _query_tokens(normalized_query)
        ranked: list[tuple[float, SourceHealthState, dict[str, object]]] = []
        sources_failed = 0
        for descriptor in descriptors:
            state = health[descriptor.source_type]
            group, score = self._build_source_group(
                descriptor,
                outcomes.get(descriptor.source_type),
                base_url=base_url,
                query_norm=query_norm,
                tokens=tokens,
                health=state,
            )
            if group["status"] == "error":
                sources_failed += 1
            ranked.append((score, state, group))

        # Demotion is the FIRST sort key, ahead of relevance: a source with a
        # failure streak sinks below every source that is still answering.
        # Relevance then orders the rest as before -- most relevant first,
        # sources with nothing to show below them, ties broken by display name
        # so the order is stable.
        #
        # Demoted is not hidden. The group, its error text and its health block
        # all survive, because the owner has to be able to SEE that a source is
        # failing -- that is the whole point -- and because one success clears
        # the streak and floats it straight back up.
        #
        # In practice a demoted source contributed nothing this round anyway
        # (that is what demoted it); this key is what keeps the empty husks of
        # ~100 dead connectors below the sources that answered.
        ranked.sort(
            key=lambda entry: (
                1 if entry[1].demoted else 0,
                -entry[0],
                0 if entry[2]["items"] else 1,
                str(entry[2]["source_name"]).casefold(),
            )
        )
        source_groups = [group for _, _, group in ranked]
        sources_demoted = sum(1 for _, state, _ in ranked if state.demoted)

        local_group: dict[str, object] = {
            "source": None,
            "source_name": _LOCAL_GROUP_NAME,
            "icon_url": None,
            "status": "ok" if local_items else "empty",
            "error": None,
            "total": len(local_items),
            "has_more": bool(local_has_more),
            "items": local_items,
        }

        # Flat list: the library first (as before), then one item per source per
        # round until the page is full.
        items = local_items[:per_page]
        if len(items) < per_page:
            items = items + _round_robin(
                [group["items"] for group in source_groups],
                per_page - len(items),
            )

        total_available = len(local_items) + sum(
            len(group["items"]) for group in source_groups
        )
        has_more = (
            local_has_more
            or total_available > len(items)
            or any(group["has_more"] for group in source_groups)
        )

        logger.info(
            "federated_search query=%r sources_queried=%d sources_failed=%d "
            "sources_demoted=%d groups_with_hits=%d items=%d",
            normalized_query,
            sources_queried,
            sources_failed,
            sources_demoted,
            sum(1 for group in source_groups if group["items"]),
            len(items),
        )

        return {
            "items": items,
            "groups": [local_group, *source_groups],
            "sources_queried": sources_queried,
            "sources_failed": sources_failed,
            # How many of the queried sources are currently demoted for a
            # failure streak. Distinct from sources_failed, which counts only
            # this search's misses.
            "sources_demoted": sources_demoted,
            "page": page,
            "has_more": has_more,
        }

    def get_series(self, source_id: str, series_id: str) -> dict[str, object]:
        connector = self._get_connector(source_id)
        series = connector.get_series(fully_unquote(series_id))
        if series is None:
            raise AppError(
                "Series not found.",
                code="series_not_found",
                status_code=404,
                details={"source_id": source_id, "series_id": series_id},
            )
        return _serialize_series(series, source_id)

    def get_chapters(self, source_id: str, series_id: str) -> list[dict[str, object]]:
        connector = self._get_connector(source_id)
        series_id = fully_unquote(series_id)
        series = connector.get_series(series_id)
        if series is None:
            raise AppError(
                "Series not found.",
                code="series_not_found",
                status_code=404,
                details={"source_id": source_id, "series_id": series_id},
            )
        chapters = connector.get_chapters(series_id)
        if not chapters and series.chapter_count > 0:
            logger.warning(
                "Chapters empty despite chapter_count=%d source=%s series=%s; retrying after cache bust",
                series.chapter_count,
                source_id,
                series_id,
            )
            _invalidate_series_caches(connector, series_id)
            series = connector.get_series(series_id)
            if series is None:
                raise AppError(
                    "Series not found.",
                    code="series_not_found",
                    status_code=404,
                    details={"source_id": source_id, "series_id": series_id},
                )
            chapters = connector.get_chapters(series_id)
        return [_serialize_chapter(chapter, source_id) for chapter in chapters]

    def get_chapter_pages(self, source_id: str, chapter_id: str) -> list[dict[str, object]]:
        connector = self._get_connector(source_id)
        normalized_chapter_id = _normalize_source_chapter_id(chapter_id)
        pages = connector.get_chapter_pages(normalized_chapter_id)
        if not pages:
            raise AppError(
                "Chapter not found.",
                code="chapter_not_found",
                status_code=404,
                details={"source_id": source_id, "chapter_id": normalized_chapter_id},
            )
        return [_serialize_page(page, source_id) for page in pages]

    def get_reader_chapter(
        self,
        source_id: str,
        series_id: str,
        chapter_id: str,
    ) -> dict[str, object]:
        connector = self._get_connector(source_id)
        normalized_chapter_id = _normalize_source_chapter_id(chapter_id)
        series_id = fully_unquote(series_id)
        series = connector.get_series(series_id)
        if series is None:
            raise AppError(
                "Series not found.",
                code="series_not_found",
                status_code=404,
            )

        chapters = connector.get_chapters(series_id)
        chapter = next((item for item in chapters if item.id == normalized_chapter_id), None)
        if chapter is None:
            raise AppError(
                "Chapter not found.",
                code="chapter_not_found",
                status_code=404,
            )

        pages = connector.get_chapter_pages(normalized_chapter_id)
        chapter_index = chapters.index(chapter)
        previous_chapter_id = chapters[chapter_index - 1].id if chapter_index > 0 else None
        next_chapter_id = (
            chapters[chapter_index + 1].id if chapter_index < len(chapters) - 1 else None
        )

        return {
            "mode": "remote",
            "source_id": source_id,
            "series_id": series_id,
            "id": normalized_chapter_id,
            "title": chapter.title,
            "number": chapter.number,
            "page_count": len(pages),
            "pages": [_serialize_page(page, source_id) for page in pages],
            "previous_chapter_id": previous_chapter_id,
            "next_chapter_id": next_chapter_id,
            "series_title": series.title,
        }

    def resolve_page_image(self, source_id: str, page_id: str) -> tuple[str, bytes]:
        connector = self._get_connector(source_id)
        normalized_page_id = fully_unquote(page_id).strip()
        page = connector.find_page(normalized_page_id)
        if page is None:
            raise AppError(
                "Page not found.",
                code="page_not_found",
                status_code=404,
                details={"source_id": source_id, "page_id": page_id},
            )
        return self._fetch_remote_image(page, connector)

    def resolve_series_cover(self, source_id: str, series_id: str) -> tuple[str, bytes]:
        connector = self._get_connector(source_id)
        series = connector.get_series(fully_unquote(series_id))
        if series is None or not series.cover_url:
            raise AppError(
                "Cover not found.",
                code="cover_not_found",
                status_code=404,
            )
        return self._fetch_url(series.cover_url, connector)

    def _fetch_remote_image(self, page: Page, connector: SourceConnector) -> tuple[str, bytes]:
        if not page.remote_url:
            raise AppError(
                "Remote page URL not available.",
                code="remote_url_missing",
                status_code=404,
            )
        return self._fetch_url(page.remote_url, connector)

    def _validate_outbound_url(self, url: str, connector: SourceConnector) -> str:
        return validate_outbound_url(url, connector)

    def _fetch_url(self, url: str, connector: SourceConnector) -> tuple[str, bytes]:
        import httpx

        self._validate_outbound_url(url, connector)

        try:
            proxied = connector.fetch_proxied_image(url)
        except ConnectorHttpError as exc:
            raise AppError(
                "Failed to fetch remote image.",
                code="remote_fetch_failed",
                status_code=502,
                details={"url": url, "reason": str(exc)},
            ) from exc
        if proxied is not None:
            return proxied

        try:
            # Redirects are not followed automatically: a redirect target
            # could point off the approved allowlist, silently bypassing it.
            # Connector headers (e.g. Referer) are required for CDNs that
            # enforce hotlink protection — bare GETs often return 403.
            response = httpx.get(
                url,
                timeout=30.0,
                follow_redirects=False,
                headers=connector.image_fetch_headers(),
            )
            if response.is_redirect:
                raise AppError(
                    "Remote host returned a redirect, which is not permitted.",
                    code="ssrf_blocked",
                    status_code=502,
                    details={"url": url},
                )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AppError(
                "Failed to fetch remote image.",
                code="remote_fetch_failed",
                status_code=502,
                details={"url": url, "reason": str(exc)},
            ) from exc

        media_type = response.headers.get("content-type", "image/jpeg").split(";")[0]
        return media_type, response.content


def get_browse_service(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[ProfileContext, Depends(resolve_profile_context)],
) -> BrowseService:
    """Per-request browse service carrying the caller's own 18+ gate.

    This is where the source-level gate becomes per-(user, profile): every
    remote read path resolves its connector through ``_get_connector``, so
    binding the gate once here covers browse, series, chapters, pages, covers
    and the reader in one place.

    The session is carried too, for source health only (read on every listing,
    written by the search fan-out when a source's state actually changes).
    """
    return BrowseService(
        mature_enabled=resolve_mature_gate(db, ctx.profile_id, ctx.user_id),
        db=db,
        user_id=ctx.user_id,
        profile_id=ctx.profile_id,
    )
