"""Automatic update engine: track series, detect new chapters, emit notifications.

Uses connectors read-only via ``connectors.registry.create_connector``.
Auto-download is gated behind per-series and global settings; the hook
``on_new_chapters`` can be wired later without modifying the download manager.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert as _sqlite_insert
from sqlalchemy.orm import Session

from connectors.models import Chapter as ConnectorChapter
from connectors.registry import (
    ConnectorDescriptor,
    create_connector,
    list_installed_connectors,
)
from core.config import get_settings
from core.content_rating import (
    TRACKER_RATING_MATURE,
    rating_from_genres,
    resolve_mature_gate,
    resolve_tracker_rating,
)
from core.errors import AppError
from core.time_utils import utcnow
from database.models import (
    Download,
    SeriesTracker,
    SourceChapterLink,
    UpdateNotification,
    UpdateRun,
    UpdateSettings,
    User,
)
from database.session import SessionLocal

logger = logging.getLogger(__name__)

# --- source migration tuning -------------------------------------------------
# Chapter numbers are matched to 3 decimal places so parser noise ("Chapter
# 10.50" vs 10.5) collapses, while genuine .5 extras/omake stay distinct --
# dropping those would silently lose the reading position inside them.
_NUMBER_PRECISION = 3
# How far back a non-exact match may reach. Matching only ever snaps BACKWARDS:
# snapping forward marks unread content as read, which cannot be undone from
# the client, whereas snapping back at worst re-shows one chapter.
_NEAREST_TOLERANCE = 1.0

NewChaptersCallback = Callable[
    [Session, SeriesTracker, list[ConnectorChapter]],
    None,
]

_on_new_chapters: NewChaptersCallback | None = None


def register_new_chapters_callback(callback: NewChaptersCallback | None) -> None:
    """Register a hook for future auto-download integration."""
    global _on_new_chapters
    _on_new_chapters = callback


def _bool(value: bool | int) -> bool:
    return bool(value)


def _load_known_ids(raw: str) -> set[str]:
    try:
        data = json.loads(raw or "[]")
        if isinstance(data, list):
            return {str(item) for item in data}
    except json.JSONDecodeError:
        pass
    return set()


def _dump_known_ids(ids: set[str]) -> str:
    return json.dumps(sorted(ids))


def _dump_known_chapters(chapters: list[ConnectorChapter]) -> str:
    """Serialize the catalog keeping each chapter's NUMBER.

    ``known_chapter_ids`` is enough for the update diff but useless for source
    migration, which maps by number. Written alongside it on every check so a
    migration off a source that later goes dark still has numbers to map with.
    """
    return json.dumps(
        [{"id": chapter.id, "number": chapter.number} for chapter in chapters]
    )


@dataclass(frozen=True, slots=True)
class ChapterRef:
    """The two facts source migration needs about a chapter: its opaque
    per-source id, and its number -- the only axis comparable across sources."""

    id: str
    number: float | None


def _load_known_chapters(raw: str | None) -> list[ChapterRef]:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    refs: list[ChapterRef] = []
    for item in data:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        number = item.get("number")
        refs.append(
            ChapterRef(
                id=str(item["id"]),
                number=float(number) if isinstance(number, (int, float)) else None,
            )
        )
    return refs


def _refs_from_chapters(chapters: list[ConnectorChapter]) -> list[ChapterRef]:
    return [ChapterRef(id=chapter.id, number=chapter.number) for chapter in chapters]


def _round_number(number: float) -> float:
    return round(number, _NUMBER_PRECISION)


def _build_chapter_map(
    old_chapters: list[ChapterRef],
    new_chapters: list[ChapterRef],
    *,
    chapter_offset: float = 0.0,
) -> list[dict[str, object]]:
    """Map old chapters onto target chapters by NUMBER.

    Ids are opaque per-source strings and titles are translations, so the number
    is the only stable axis -- the update engine already treats it as the
    ordering authority (see ``_chapter_sort_key``).

    ``chapter_offset`` is added to every old number before matching, for targets
    that restart numbering per season or are simply offset. No cleverness is
    attempted beyond that: the dry run reports ``counts.matched`` so the UI can
    let the user nudge the offset until the match count peaks, which is
    deterministic and self-explanatory in a way that heuristics are not.
    """
    by_number: dict[float, str] = {}
    for chapter in new_chapters:
        if chapter.number is None:
            continue
        key = _round_number(chapter.number)
        # First occurrence wins: a catalog listing the same number twice is a
        # duplicate row, and the earlier one is the canonical entry.
        by_number.setdefault(key, chapter.id)
    sorted_numbers = sorted(by_number)

    mapping: list[dict[str, object]] = []
    for chapter in old_chapters:
        if chapter.number is None:
            # Unnumbered on the old side: nothing to match against. Reported
            # rather than guessed -- a wrong guess silently moves the user's
            # place in a chapter they have not read.
            mapping.append(
                {
                    "from_chapter_id": chapter.id,
                    "number": None,
                    "to_chapter_id": None,
                    "match": "none",
                }
            )
            continue

        wanted = _round_number(chapter.number + chapter_offset)
        target_id = by_number.get(wanted)
        if target_id is not None:
            mapping.append(
                {
                    "from_chapter_id": chapter.id,
                    "number": chapter.number,
                    "to_chapter_id": target_id,
                    "match": "exact",
                }
            )
            continue

        # Nearest target at or BELOW the wanted number, within tolerance.
        candidate: float | None = None
        for number in sorted_numbers:
            if number > wanted:
                break
            candidate = number
        if candidate is not None and wanted - candidate <= _NEAREST_TOLERANCE:
            mapping.append(
                {
                    "from_chapter_id": chapter.id,
                    "number": chapter.number,
                    "to_chapter_id": by_number[candidate],
                    "match": "nearest",
                }
            )
        else:
            mapping.append(
                {
                    "from_chapter_id": chapter.id,
                    "number": chapter.number,
                    "to_chapter_id": None,
                    "match": "none",
                }
            )
    return mapping


def _chapter_map_hash(mapping: list[dict[str, object]]) -> str:
    """Stable hash over the ordered (from, to) pairs.

    The commit compares this against the hash the user was shown, so a target
    that gained chapters between preview and confirm is refused rather than
    silently applying a map nobody saw."""
    digest = hashlib.sha256()
    for entry in mapping:
        digest.update(str(entry["from_chapter_id"]).encode("utf-8"))
        digest.update(b"\x00")
        digest.update(str(entry["to_chapter_id"] or "").encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


class UpdateService:
    """Business logic for the automatic update subsystem."""

    def __init__(
        self,
        db: Session,
        user_id: int | None = None,
        profile_id: int | None = None,
    ) -> None:
        self._db = db
        # Follows and notifications are per-(user, profile). The background
        # scheduler runs with user_id=None/profile_id=None but never uses them to
        # scope — it checks every user's trackers and stamps each notification
        # with the tracker's own owner + profile.
        self._user_id = user_id
        self._profile_id = profile_id
        self._descriptor_cache: dict[str, ConnectorDescriptor] | None = None

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def get_global_settings(self) -> UpdateSettings:
        # Fast path: row already in DB (normal case after first startup).
        row = self._db.get(UpdateSettings, 1)
        if row is not None:
            return row

        # Slow path: first ever startup. Use INSERT OR IGNORE so concurrent
        # sessions racing here (scheduler thread vs main thread) can never
        # collide on the UNIQUE primary-key constraint.
        config = get_settings()
        self._db.execute(
            _sqlite_insert(UpdateSettings)
            .values(
                id=1,
                enabled=True,
                check_interval_minutes=config.update_check_interval_minutes,
                notify_enabled=True,
                auto_download_enabled=False,
                check_on_startup=True,
            )
            .on_conflict_do_nothing()
        )
        row = self._db.get(UpdateSettings, 1)
        assert row is not None, "update_settings singleton (id=1) missing after upsert"
        return row

    def update_global_settings(self, payload: dict[str, Any]) -> dict[str, object]:
        row = self.get_global_settings()
        if "enabled" in payload:
            row.enabled = bool(payload["enabled"])
        if "check_interval_minutes" in payload:
            minutes = int(payload["check_interval_minutes"])
            if minutes < 5:
                raise AppError("check_interval_minutes must be at least 5", status_code=400)
            row.check_interval_minutes = minutes
        if "notify_enabled" in payload:
            row.notify_enabled = bool(payload["notify_enabled"])
        if "auto_download_enabled" in payload:
            row.auto_download_enabled = bool(payload["auto_download_enabled"])
        if "check_on_startup" in payload:
            row.check_on_startup = bool(payload["check_on_startup"])
        self._db.flush()
        self._db.commit()
        return self.serialize_settings(row)

    def serialize_settings(self, row: UpdateSettings) -> dict[str, object]:
        return {
            "enabled": _bool(row.enabled),
            "check_interval_minutes": row.check_interval_minutes,
            "notify_enabled": _bool(row.notify_enabled),
            "auto_download_enabled": _bool(row.auto_download_enabled),
            "check_on_startup": _bool(row.check_on_startup),
            "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    # ------------------------------------------------------------------
    # Trackers
    # ------------------------------------------------------------------

    # ---- maturity -----------------------------------------------------

    def _mature_enabled(self) -> bool:
        """The active 18+ gate for this (user, profile)."""
        return resolve_mature_gate(self._db, self._profile_id, self._user_id)

    def _descriptors_by_source(self) -> dict[str, ConnectorDescriptor]:
        """Every installed connector keyed by id, mature ones included.

        Deliberately unfiltered: resolving a tracker's rating needs to know that
        its source IS adult, which a mature-excluded listing cannot tell us.

        Cached per service instance (i.e. per request): a single GET /trackers
        resolves ratings for the list, the count, and the hidden count, and the
        registry cannot change mid-request.
        """
        if self._descriptor_cache is None:
            self._descriptor_cache = {
                descriptor.source_type: descriptor
                for descriptor in list_installed_connectors(include_mature=True)
            }
        return self._descriptor_cache

    def _tracker_rating(
        self,
        row: SeriesTracker,
        descriptors: dict[str, ConnectorDescriptor] | None = None,
    ) -> str:
        lookup = descriptors if descriptors is not None else self._descriptors_by_source()
        return resolve_tracker_rating(row, lookup.get(row.source))

    def _scoped_trackers(self, *, track_kind: str | None, source: str | None):
        query = self._db.query(SeriesTracker).filter(
            SeriesTracker.user_id == self._user_id,
            SeriesTracker.profile_id == self._profile_id,
        )
        if track_kind:
            query = query.filter(SeriesTracker.track_kind == track_kind)
        if source:
            query = query.filter(SeriesTracker.source == source)
        return query

    def _visible_trackers(
        self, *, track_kind: str | None = None, source: str | None = None
    ) -> list[SeriesTracker]:
        """Trackers this (user, profile) may see right now, gate applied.

        The rating is resolved in Python rather than SQL because two of its
        three inputs are not columns -- the user's override and the *source's*
        maturity, which lives in the connector registry, not the database.
        The row set is one profile's follows, so this is bounded and cheap.
        """
        rows = (
            self._scoped_trackers(track_kind=track_kind, source=source)
            .order_by(SeriesTracker.series_title)
            .all()
        )
        if self._mature_enabled():
            return rows
        descriptors = self._descriptors_by_source()
        return [
            row
            for row in rows
            if self._tracker_rating(row, descriptors) != TRACKER_RATING_MATURE
        ]

    def list_trackers(
        self,
        *,
        track_kind: str | None = None,
        source: str | None = None,
    ) -> list[dict[str, object]]:
        descriptors = self._descriptors_by_source()
        return [
            self.serialize_tracker(row, descriptors=descriptors)
            for row in self._visible_trackers(track_kind=track_kind, source=source)
        ]

    def count_trackers(
        self,
        *,
        track_kind: str | None = None,
        source: str | None = None,
    ) -> int:
        # Counts the *visible* rows so the X-Total-Count header agrees with the
        # body; the hidden ones are reported separately by ``hidden_by_gate``.
        return len(self._visible_trackers(track_kind=track_kind, source=source))

    def count_trackers_hidden_by_gate(
        self,
        *,
        track_kind: str | None = None,
        source: str | None = None,
    ) -> int:
        """How many follows the 18+ gate is currently hiding.

        Surfaced so a follow list that suddenly shrinks reads as "3 hidden by
        the 18+ filter" rather than as data loss -- the single most likely way
        this change gets mistaken for a bug.
        """
        if self._mature_enabled():
            return 0
        total = self._scoped_trackers(track_kind=track_kind, source=source).count()
        return total - len(
            self._visible_trackers(track_kind=track_kind, source=source)
        )

    def serialize_tracker(
        self,
        row: SeriesTracker,
        descriptors: dict[str, ConnectorDescriptor] | None = None,
    ) -> dict[str, object]:
        known = _load_known_ids(row.known_chapter_ids)
        return {
            "id": row.id,
            "source": row.source,
            "source_id": row.source,
            "series_id": row.series_id,
            "series_title": row.series_title,
            "track_kind": row.track_kind,
            "local_series_id": row.local_series_id,
            "enabled": _bool(row.enabled),
            "notify": _bool(row.notify),
            "auto_download": _bool(row.auto_download),
            "check_interval_minutes": row.check_interval_minutes,
            "known_chapter_count": len(known),
            # "mature" | "safe" | "unknown". Unknown is a real state, not a
            # softer "safe": the client badges it and offers the one-tap
            # override that writes mature_override.
            "rating": self._tracker_rating(row, descriptors),
            "content_rating": row.content_rating,
            "mature_override": (
                None if row.mature_override is None else bool(row.mature_override)
            ),
            "migrated_from_source": row.migrated_from_source,
            "migrated_from_series_id": row.migrated_from_series_id,
            "migrated_at": row.migrated_at.isoformat() if row.migrated_at else None,
            "last_checked_at": row.last_checked_at.isoformat() if row.last_checked_at else None,
            "last_error": row.last_error,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    def follow_series(
        self,
        *,
        source: str,
        series_id: str,
        series_title: str,
        genres: list[str] | None = None,
    ) -> dict[str, object]:
        self._ensure_browsable_source(source)
        # Scoped to this (user, profile): the composite unique now includes
        # profile_id, so a second profile on the same account follows the same
        # remote series as its OWN independent row rather than colliding on the
        # first profile's tracker.
        existing = (
            self._db.query(SeriesTracker)
            .filter(
                SeriesTracker.user_id == self._user_id,
                SeriesTracker.profile_id == self._profile_id,
                SeriesTracker.source == source,
                SeriesTracker.series_id == series_id,
                SeriesTracker.track_kind == "followed",
            )
            .first()
        )
        if existing is not None:
            return self.serialize_tracker(existing)

        row = SeriesTracker(
            user_id=self._user_id,
            profile_id=self._profile_id,
            source=source,
            series_id=series_id,
            series_title=series_title,
            track_kind="followed",
            # Rating snapshot taken from the genres the caller already has in
            # hand (it is following from the series page it just rendered).
            # Deliberately NOT re-fetched from the connector here: a follow must
            # not block on a scraper, and half the registry is dead anyway. A
            # miss degrades to *unknown* — badged and overridable — never
            # silently to "safe", and an adult source is caught regardless by
            # resolve_tracker_rating's source rule.
            content_rating=rating_from_genres(genres),
        )
        self._db.add(row)
        self._db.flush()
        self._db.commit()
        return self.serialize_tracker(row)

    def unfollow_tracker(self, tracker_id: int) -> None:
        row = self._require_tracker(tracker_id)
        if row.track_kind == "downloaded":
            raise AppError("Downloaded series trackers cannot be removed directly", status_code=400)
        self._db.delete(row)
        self._db.commit()

    def update_tracker(self, tracker_id: int, payload: dict[str, Any]) -> dict[str, object]:
        row = self._require_tracker(tracker_id)
        if "enabled" in payload:
            row.enabled = bool(payload["enabled"])
        if "notify" in payload:
            row.notify = bool(payload["notify"])
        if "auto_download" in payload:
            row.auto_download = bool(payload["auto_download"])
        if "check_interval_minutes" in payload:
            value = payload["check_interval_minutes"]
            if value is None:
                row.check_interval_minutes = None
            else:
                minutes = int(value)
                if minutes < 5:
                    raise AppError("check_interval_minutes must be at least 5", status_code=400)
                row.check_interval_minutes = minutes
        if "series_title" in payload and payload["series_title"]:
            row.series_title = str(payload["series_title"])
        if "mature_override" in payload:
            # Tri-state: True = "this is 18+", False = "this is not",
            # None = "go back to inferring". Kept explicit rather than folded
            # into content_rating so the user's verdict is never overwritten by
            # a later metadata refresh.
            value = payload["mature_override"]
            row.mature_override = None if value is None else bool(value)
        self._db.flush()
        self._db.commit()
        return self.serialize_tracker(row)

    def sync_downloaded_trackers(self) -> dict[str, object]:
        """Create or refresh downloaded-series trackers from completed downloads."""
        rows = (
            self._db.query(
                Download.source,
                Download.series_id,
                func.max(Download.series_title).label("series_title"),
            )
            .filter(
                Download.status == "completed",
                Download.user_id == self._user_id,
                # Profile too, not just the account. The trackers minted below
                # are stamped with self._profile_id, so selecting on user alone
                # made one profile's sync create "downloaded" trackers for a
                # sibling profile's downloads -- attributing content to a
                # persona that never asked for it. Downloads only gained a
                # profile_id in b8f52d1c47ae; rows predating it are NULL and are
                # picked up by the account's unscoped bucket, which is where
                # their membership landed too.
                Download.profile_id == self._profile_id,
            )
            .group_by(Download.source, Download.series_id)
            .all()
        )
        created = 0
        updated = 0
        for source, series_id, series_title in rows:
            tracker = (
                self._db.query(SeriesTracker)
                .filter(
                    SeriesTracker.user_id == self._user_id,
                    SeriesTracker.profile_id == self._profile_id,
                    SeriesTracker.source == source,
                    SeriesTracker.series_id == series_id,
                    SeriesTracker.track_kind == "downloaded",
                )
                .first()
            )
            if tracker is None:
                self._db.add(
                    SeriesTracker(
                        user_id=self._user_id,
                        profile_id=self._profile_id,
                        source=source,
                        series_id=series_id,
                        series_title=series_title or series_id,
                        track_kind="downloaded",
                    )
                )
                created += 1
            elif series_title and tracker.series_title != series_title:
                tracker.series_title = series_title
                updated += 1
        self._db.flush()
        self._db.commit()
        return {"created": created, "updated": updated, "total": len(rows)}

    # ------------------------------------------------------------------
    # Source migration (repoint a follow at another source)
    # ------------------------------------------------------------------

    async def list_migration_candidates(
        self,
        tracker_id: int,
        *,
        browse,
        query: str | None = None,
        base_url: str = "",
        per_page: int = 10,
    ) -> dict[str, object]:
        """Candidate targets for repointing ``tracker_id`` at another source.

        Reuses ``BrowseService.federated_search`` rather than adding a second
        fan-out: it already queries every browsable source in parallel, scores
        and sorts the hits, honours the 18+ gate, and reports which sources
        failed. This is the ~30-line wrapper on top -- defaulting the query to
        the followed title, dropping the local library and the source being left
        behind, and keeping the best hit per remaining source.

        Inherits the fan-out's partial-failure semantics: with a registry this
        size ``sources_failed`` is routinely large and is normal, not an error.
        """
        tracker = self._require_tracker(tracker_id)
        search_query = (query or tracker.series_title or "").strip()

        result = await browse.federated_search(
            search_query,
            page=1,
            per_page=max(per_page, 1),
            include_mature=self._mature_enabled(),
            base_url=base_url,
        )

        candidates: list[dict[str, object]] = []
        for group in result.get("groups", []):
            source = group.get("source")
            # ``None`` is the local-library group; the tracker's own source is
            # the thing being migrated away from.
            if source is None or source == tracker.source:
                continue
            items = group.get("items") or []
            if not items:
                continue
            best = items[0]
            candidates.append(
                {
                    "source": source,
                    "source_name": group.get("source_name"),
                    "icon_url": group.get("icon_url"),
                    "series_id": best.get("series_id"),
                    "title": best.get("title"),
                    "cover_url": best.get("cover_url"),
                    "author": best.get("author"),
                    "chapter_count": best.get("chapter_count") or None,
                }
            )

        return {
            "tracker": self.serialize_tracker(tracker),
            "query": search_query,
            "candidates": candidates,
            "sources_queried": result.get("sources_queried", 0),
            "sources_failed": result.get("sources_failed", 0),
        }

    def _fetch_catalog(self, source: str, series_id: str) -> list[ChapterRef] | None:
        """Chapter refs for one (source, series), or ``None`` if unreachable."""
        try:
            return _refs_from_chapters(create_connector(source).get_chapters(series_id))
        except Exception as exc:  # noqa: BLE001 - a dead source is the normal case here
            logger.info("migration: catalog fetch failed for %s/%s: %s", source, series_id, exc)
            return None

    def plan_migration(
        self,
        tracker_id: int,
        *,
        target_source: str,
        target_series_id: str,
        chapter_offset: float = 0.0,
    ) -> dict[str, object]:
        """Compute the remap without touching the database.

        Both catalogs are fetched HERE, before any write transaction is opened:
        holding a write open across a scraper call (search runs on an 8s budget,
        browse on 30s x 3) would pin the database for the length of someone
        else's outage.
        """
        tracker = self._require_tracker(tracker_id)
        self._validate_migration_target(
            tracker, target_source=target_source, target_series_id=target_series_id
        )

        new_chapters = self._fetch_catalog(target_source, target_series_id)
        if new_chapters is None:
            raise AppError(
                f"Could not read the chapter list from '{target_source}'.",
                code="migration_target_unreachable",
                status_code=502,
                details={"source": target_source, "series_id": target_series_id},
            )

        # The old source being dead is the whole reason this feature exists, so
        # its catalog is best-effort: fall back to the numbers recorded at the
        # last successful check, and if even those are absent report it rather
        # than pretending the map is empty because nothing matched.
        old_chapters = self._fetch_catalog(tracker.source, tracker.series_id)
        old_catalog = "ok"
        if old_chapters is None:
            old_chapters = _load_known_chapters(tracker.known_chapters)
            old_catalog = "cached" if old_chapters else "unavailable"

        mapping = _build_chapter_map(
            old_chapters, new_chapters, chapter_offset=chapter_offset
        )
        matched = [entry for entry in mapping if entry["to_chapter_id"]]
        mapped_targets = {entry["to_chapter_id"] for entry in matched}

        warnings: list[str] = []
        if old_catalog == "unavailable":
            warnings.append(
                f"'{tracker.source}' could not be read and no cached chapter numbers "
                "were recorded, so no reading progress can be remapped. The follow "
                "will be repointed and your existing progress left untouched."
            )
        elif old_catalog == "cached":
            warnings.append(
                f"'{tracker.source}' could not be read; the remap was computed from "
                "the chapter list recorded at the last successful update check."
            )
        unmapped = [entry for entry in mapping if not entry["to_chapter_id"]]
        if unmapped:
            highest = max(
                (entry["number"] for entry in matched if entry["number"] is not None),
                default=None,
            )
            above = f" above #{highest:g}" if highest is not None else ""
            warnings.append(
                f"Progress on {len(unmapped)} chapter(s){above} has no equivalent "
                "on the target and cannot be carried over."
            )
        if len(new_chapters) < len(old_chapters):
            warnings.append(
                f"The target has {len(old_chapters) - len(new_chapters)} fewer "
                "chapters than the source you are leaving."
            )

        siblings = [
            {"id": row.id, "track_kind": row.track_kind}
            for row in self._scoped_trackers(track_kind=None, source=tracker.source)
            .filter(
                SeriesTracker.series_id == tracker.series_id,
                SeriesTracker.id != tracker.id,
            )
            .all()
        ]

        return {
            "tracker_id": tracker.id,
            "from": {"source": tracker.source, "series_id": tracker.series_id},
            "to": {"source": target_source, "series_id": target_series_id},
            "old_catalog": old_catalog,
            "chapter_map": mapping,
            "unmatched_source_chapters": [
                entry["from_chapter_id"] for entry in unmapped
            ],
            "target_only_chapters": [
                chapter.id for chapter in new_chapters if chapter.id not in mapped_targets
            ],
            "counts": {
                "old": len(old_chapters),
                "new": len(new_chapters),
                "matched": len(matched),
                "dropped": len(unmapped),
            },
            "chapter_map_hash": _chapter_map_hash(mapping),
            "warnings": warnings,
            "sibling_trackers": siblings,
            "_new_chapters": new_chapters,
        }

    def _validate_migration_target(
        self,
        tracker: SeriesTracker,
        *,
        target_source: str,
        target_series_id: str,
    ) -> None:
        if tracker.track_kind == "downloaded":
            # Mirrors unfollow_tracker: a downloaded tracker is derived from the
            # Download rows, so sync_downloaded_trackers would simply recreate
            # it at the old source on the next sync. The response lists sibling
            # trackers so the client can offer to migrate the followed one.
            raise AppError(
                "Downloaded series trackers cannot be migrated; migrate the "
                "followed tracker for this series instead.",
                code="migration_track_kind_unsupported",
                status_code=400,
            )
        if not target_series_id.strip():
            raise AppError(
                "target_series_id must not be empty.",
                code="validation_error",
                status_code=422,
            )
        # Gate-aware, so migration cannot become a back door onto an 18+ source
        # while the profile has adult content turned off.
        self._ensure_browsable_source(target_source)

    def migrate_tracker(
        self,
        tracker_id: int,
        *,
        target_source: str,
        target_series_id: str,
        target_series_title: str | None = None,
        chapter_offset: float = 0.0,
        dry_run: bool = True,
        merge: bool = False,
        expected_chapter_map_hash: str | None = None,
    ) -> dict[str, object]:
        """Repoint a follow at another source, preserving progress.

        Preview and commit share one code path and one response shape, so the
        map a user confirms is computed exactly the way the map they were shown
        was. ``dry_run`` only decides whether the writes happen.
        """
        tracker = self._require_tracker(tracker_id)

        # Idempotency: a client retrying after a dropped response finds the
        # tracker already at the target and gets the same freshly-recomputed
        # remap with no second set of side effects.
        already_there = (
            tracker.source == target_source and tracker.series_id == target_series_id
        )

        plan = self.plan_migration(
            tracker_id,
            target_source=target_source,
            target_series_id=target_series_id,
            chapter_offset=chapter_offset,
        )
        new_chapters: list[ChapterRef] = plan.pop("_new_chapters")
        plan["notifications_rewritten"] = 0
        plan["notifications_dropped"] = 0
        plan["downloads_relinked"] = 0
        plan["merged_into_tracker_id"] = None

        if dry_run or already_there:
            plan["applied"] = False
            return plan

        if (
            expected_chapter_map_hash
            and expected_chapter_map_hash != plan["chapter_map_hash"]
        ):
            raise AppError(
                "The target's chapter list changed since the preview.",
                code="migration_stale",
                status_code=409,
                details={"preview": plan},
            )

        conflict = (
            self._scoped_trackers(track_kind=tracker.track_kind, source=target_source)
            .filter(
                SeriesTracker.series_id == target_series_id,
                SeriesTracker.id != tracker.id,
            )
            .first()
        )
        if conflict is not None and not merge:
            # uq_series_tracker (user_id, profile_id, source, series_id,
            # track_kind) would reject the UPDATE. Refusing by default rather
            # than merging silently: the two rows can carry different notify /
            # auto_download / interval settings and different known-chapter
            # sets, and picking a winner for the user is exactly the kind of
            # invisible decision that shows up later as "it stopped notifying
            # me". Merge stays available as an explicit opt-in.
            raise AppError(
                "You already follow that series on that source.",
                code="tracker_target_already_followed",
                status_code=409,
                details={
                    "existing_tracker_id": conflict.id,
                    "hint": "Retry with merge=true to combine the two follows.",
                },
            )

        try:
            counts = self._apply_migration(
                tracker,
                conflict=conflict,
                target_source=target_source,
                target_series_id=target_series_id,
                target_series_title=target_series_title,
                new_chapters=new_chapters,
                chapter_map=plan["chapter_map"],
            )
            self._db.commit()
        except Exception:
            # One transaction, one commit: a failure anywhere above leaves the
            # tracker, its notifications and its download links exactly as they
            # were. A half-migrated follow is impossible by construction.
            self._db.rollback()
            raise

        plan.update(counts)
        plan["applied"] = True
        return plan

    def _apply_migration(
        self,
        tracker: SeriesTracker,
        *,
        conflict: SeriesTracker | None,
        target_source: str,
        target_series_id: str,
        target_series_title: str | None,
        new_chapters: list[ChapterRef],
        chapter_map: list[dict[str, object]],
    ) -> dict[str, object]:
        """Every write the migration performs, in one transaction.

        Deliberately left alone (and why):

        * ``Download`` rows -- a historical job log keyed on (source, series_id,
          chapter_id). Rewriting them corrupts the audit trail and makes
          ``sync_downloaded_trackers`` mint a second "downloaded" tracker for
          the new source. They also carry no profile_id, so they cannot be
          scoped to the migrating profile in the first place.
        * ``ReadingProgress`` / ``ChapterProgress`` / ``UserSeriesState`` /
          ``Bookmark`` -- all keyed on LOCAL chapter and series ids, which a
          source repoint does not touch.
        * ``local_series_id`` -- the local folder is unchanged by a repoint.
        """
        old_source = tracker.source
        old_series_id = tracker.series_id
        remap = {
            str(entry["from_chapter_id"]): str(entry["to_chapter_id"])
            for entry in chapter_map
            if entry["to_chapter_id"]
        }

        # --- downloads already on disk stay reachable -----------------------
        # SourceChapterLink records where bytes actually came from, so rewriting
        # it would claim the target served files it never served (and collide on
        # uq_source_chapter as soon as the target's own downloads arrive).
        # Instead an ADDITIONAL link is inserted under the new (source,
        # series_id), so ReadingService._find_local_chapter resolves either id
        # and a chapter already on disk is not re-streamed from the network.
        relinked = 0
        if remap:
            existing_links = {
                link.chapter_id: link
                for link in self._db.query(SourceChapterLink).filter(
                    SourceChapterLink.source == old_source,
                    SourceChapterLink.series_id == old_series_id,
                    SourceChapterLink.chapter_id.in_(remap),
                )
            }
            already_linked = {
                link.chapter_id
                for link in self._db.query(SourceChapterLink).filter(
                    SourceChapterLink.source == target_source,
                    SourceChapterLink.series_id == target_series_id,
                )
            }
            # At most one link per target chapter: nearest-match can collapse
            # two old chapters onto one target, which would violate
            # uq_source_chapter. Guarded explicitly rather than caught as an
            # IntegrityError, because the same transaction also carries the
            # tracker and notification rewrites.
            for from_id, to_id in remap.items():
                link = existing_links.get(from_id)
                if link is None or to_id in already_linked:
                    continue
                already_linked.add(to_id)
                self._db.add(
                    SourceChapterLink(
                        source=target_source,
                        series_id=target_series_id,
                        chapter_id=to_id,
                        local_chapter_id=link.local_chapter_id,
                    )
                )
                relinked += 1

        # --- notifications --------------------------------------------------
        surviving = conflict if conflict is not None else tracker
        rewritten = 0
        dropped = 0
        for note in list(tracker.notifications):
            mapped = remap.get(note.chapter_id)
            if mapped is None:
                # A notification whose chapter no longer resolves on the new
                # source is a dead link that 404s in the reader; deleting it is
                # already a supported shape (cascade="all, delete-orphan").
                self._db.delete(note)
                dropped += 1
                continue
            # Reassigned through the RELATIONSHIP, not the foreign key column:
            # on the merge path the loser tracker is deleted below, and its
            # delete-orphan cascade takes anything still sitting in
            # ``tracker.notifications`` — which a bare tracker_id write would
            # leave it in.
            note.tracker = surviving
            note.source = target_source
            note.series_id = target_series_id
            note.chapter_id = mapped
            if target_series_title:
                note.series_title = target_series_title
            rewritten += 1

        target_ids = {chapter.id for chapter in new_chapters}

        if conflict is not None:
            # Merge: the row already at the target survives, this one is folded
            # into it. Union the known ids so the first post-merge check does
            # not treat the union's difference as brand-new chapters.
            merged_known = _load_known_ids(conflict.known_chapter_ids) | target_ids
            conflict.known_chapter_ids = _dump_known_ids(merged_known)
            conflict.known_chapters = json.dumps(
                [{"id": c.id, "number": c.number} for c in new_chapters]
            )
            conflict.migrated_from_source = old_source
            conflict.migrated_from_series_id = old_series_id
            conflict.migrated_at = utcnow()
            # An 18+ follow must not be laundered into a safe one by merging.
            if conflict.mature_override is None and tracker.mature_override is not None:
                conflict.mature_override = tracker.mature_override
            if not conflict.content_rating and tracker.content_rating:
                conflict.content_rating = tracker.content_rating
            self._db.flush()
            self._db.delete(tracker)
        else:
            tracker.source = target_source
            tracker.series_id = target_series_id
            if target_series_title:
                tracker.series_title = target_series_title
            # Reset to the TARGET's full id set. Leaving the old source's ids
            # here would make the first post-migration check see the entire
            # target catalog as new and emit one notification per chapter.
            tracker.known_chapter_ids = _dump_known_ids(target_ids)
            tracker.known_chapters = json.dumps(
                [{"id": c.id, "number": c.number} for c in new_chapters]
            )
            tracker.migrated_from_source = old_source
            tracker.migrated_from_series_id = old_series_id
            tracker.migrated_at = utcnow()
            # content_rating / mature_override are deliberately NOT cleared: a
            # follow the user (or the backfill) marked 18+ must not become
            # visible again just because it now lives on a general-purpose
            # source.
            tracker.last_checked_at = None
            tracker.last_error = None

        self._db.flush()
        return {
            "notifications_rewritten": rewritten,
            "notifications_dropped": dropped,
            "downloads_relinked": relinked,
            "merged_into_tracker_id": conflict.id if conflict is not None else None,
        }

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    def list_notifications(
        self,
        *,
        unread_only: bool = False,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        query = (
            self._db.query(UpdateNotification)
            .filter(
                UpdateNotification.user_id == self._user_id,
                UpdateNotification.profile_id == self._profile_id,
            )
            .order_by(UpdateNotification.created_at.desc())
        )
        if unread_only:
            query = query.filter(UpdateNotification.is_read.is_(False))
        rows = query.limit(max(1, min(limit, 500))).all()
        return [self.serialize_notification(row) for row in rows]

    def count_notifications(self, *, unread_only: bool = False) -> int:
        query = self._db.query(UpdateNotification).filter(
            UpdateNotification.user_id == self._user_id,
            UpdateNotification.profile_id == self._profile_id,
        )
        if unread_only:
            query = query.filter(UpdateNotification.is_read.is_(False))
        return query.count()

    def unread_count(self) -> int:
        return (
            self._db.query(UpdateNotification)
            .filter(
                UpdateNotification.user_id == self._user_id,
                UpdateNotification.profile_id == self._profile_id,
                UpdateNotification.is_read.is_(False),
            )
            .count()
        )

    def serialize_notification(self, row: UpdateNotification) -> dict[str, object]:
        return {
            "id": row.id,
            "tracker_id": row.tracker_id,
            "source": row.source,
            "source_id": row.source,
            "series_id": row.series_id,
            "series_title": row.series_title,
            "chapter_id": row.chapter_id,
            "chapter_title": row.chapter_title,
            "chapter_number": row.chapter_number,
            "is_read": _bool(row.is_read),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def mark_notification_read(self, notification_id: int) -> dict[str, object]:
        row = (
            self._db.query(UpdateNotification)
            .filter(
                UpdateNotification.id == notification_id,
                UpdateNotification.user_id == self._user_id,
                UpdateNotification.profile_id == self._profile_id,
            )
            .first()
        )
        if row is None:
            raise AppError("Notification not found", status_code=404)
        row.is_read = True
        self._db.flush()
        self._db.commit()
        return self.serialize_notification(row)

    def mark_all_notifications_read(self) -> dict[str, int]:
        count = (
            self._db.query(UpdateNotification)
            .filter(
                UpdateNotification.user_id == self._user_id,
                UpdateNotification.profile_id == self._profile_id,
                UpdateNotification.is_read.is_(False),
            )
            .update({UpdateNotification.is_read: True})
        )
        self._db.commit()
        return {"marked_read": count}

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    def list_runs(self, *, limit: int = 20) -> list[dict[str, object]]:
        rows = (
            self._db.query(UpdateRun)
            .order_by(UpdateRun.started_at.desc())
            .limit(max(1, min(limit, 100)))
            .all()
        )
        return [self.serialize_run(row) for row in rows]

    def count_runs(self) -> int:
        return self._db.query(UpdateRun).count()

    def get_run(self, run_id: int) -> dict[str, object]:
        row = self._db.query(UpdateRun).filter(UpdateRun.id == run_id).first()
        if row is None:
            raise AppError("Update run not found", status_code=404)
        return self.serialize_run(row)

    def serialize_run(self, row: UpdateRun) -> dict[str, object]:
        return {
            "id": row.id,
            "trigger": row.trigger,
            "status": row.status,
            "series_checked": row.series_checked,
            "new_chapters_found": row.new_chapters_found,
            "error": row.error,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        }

    # ------------------------------------------------------------------
    # Check engine
    # ------------------------------------------------------------------

    def run_check(
        self,
        *,
        trigger: str = "manual",
        tracker_ids: list[int] | None = None,
    ) -> dict[str, object]:
        settings = self.get_global_settings()
        if not _bool(settings.enabled) and trigger == "scheduled":
            return {"skipped": True, "reason": "updates_disabled"}

        run = UpdateRun(trigger=trigger, status="running")
        self._db.add(run)
        self._db.flush()

        try:
            trackers = self._select_trackers_for_check(tracker_ids)
            force = tracker_ids is not None
            new_total = 0
            checked = 0
            for tracker in trackers:
                if not force and not self._is_due(tracker, settings):
                    continue
                new_count = self._check_tracker(tracker, settings)
                new_total += new_count
                checked += 1

            run.status = "completed"
            run.series_checked = checked
            run.new_chapters_found = new_total
            run.finished_at = utcnow()
            settings.last_run_at = run.finished_at
            self._db.flush()
            return self.serialize_run(run)
        except Exception as exc:
            run.status = "failed"
            run.error = str(exc)
            run.finished_at = utcnow()
            self._db.flush()
            logger.exception("Update check failed")
            raise

    def check_tracker_by_id(self, tracker_id: int) -> dict[str, object]:
        tracker = self._require_tracker(tracker_id)
        settings = self.get_global_settings()
        new_count = self._check_tracker(tracker, settings)
        return {
            "tracker_id": tracker_id,
            "new_chapters": new_count,
            "tracker": self.serialize_tracker(tracker),
        }

    def _select_trackers_for_check(self, tracker_ids: list[int] | None) -> list[SeriesTracker]:
        query = self._db.query(SeriesTracker).filter(SeriesTracker.enabled.is_(True))
        # Scoped when a request is driving this, global when the scheduler is.
        # POST /updates/check accepts explicit tracker_ids, and without this a
        # caller could name another account's tracker id and force a check of
        # it. The background sweep constructs this service with no user context
        # precisely because it must cover every household member, so scoping
        # unconditionally would silently stop update checking altogether.
        if self._user_id is not None:
            query = query.filter(
                SeriesTracker.user_id == self._user_id,
                SeriesTracker.profile_id == self._profile_id,
            )
        if tracker_ids:
            query = query.filter(SeriesTracker.id.in_(tracker_ids))
        return query.order_by(SeriesTracker.source, SeriesTracker.series_title).all()

    def _is_due(self, tracker: SeriesTracker, settings: UpdateSettings) -> bool:
        if tracker.last_checked_at is None:
            return True
        interval = tracker.check_interval_minutes or settings.check_interval_minutes
        due_at = tracker.last_checked_at + timedelta(minutes=interval)
        return utcnow() >= due_at

    def _check_tracker(self, tracker: SeriesTracker, settings: UpdateSettings) -> int:
        try:
            connector = create_connector(tracker.source)
            remote_chapters = connector.get_chapters(tracker.series_id)
        except Exception as exc:
            tracker.last_error = str(exc)
            tracker.last_checked_at = utcnow()
            self._db.flush()
            logger.warning(
                "Failed to check %s/%s: %s",
                tracker.source,
                tracker.series_id,
                exc,
            )
            return 0

        known_ids = _load_known_ids(tracker.known_chapter_ids)
        remote_by_id = {chapter.id: chapter for chapter in remote_chapters}
        remote_ids = set(remote_by_id)

        if not known_ids:
            tracker.known_chapter_ids = _dump_known_ids(remote_ids)
            tracker.known_chapters = _dump_known_chapters(remote_chapters)
            tracker.last_checked_at = utcnow()
            tracker.last_error = None
            self._db.flush()
            return 0

        new_ids = sorted(remote_ids - known_ids, key=lambda cid: _chapter_sort_key(remote_by_id[cid]))
        new_chapters = [remote_by_id[cid] for cid in new_ids]
        notify_enabled = _bool(settings.notify_enabled) and _bool(tracker.notify)

        if new_chapters and notify_enabled:
            for chapter in new_chapters:
                self._db.add(
                    UpdateNotification(
                        user_id=tracker.user_id,
                        profile_id=tracker.profile_id,
                        tracker_id=tracker.id,
                        source=tracker.source,
                        series_id=tracker.series_id,
                        series_title=tracker.series_title,
                        chapter_id=chapter.id,
                        chapter_title=chapter.title,
                        chapter_number=chapter.number,
                    )
                )

        auto_download = (
            _bool(settings.auto_download_enabled)
            and _bool(tracker.auto_download)
            and bool(new_chapters)
        )
        if auto_download and _on_new_chapters is not None:
            _on_new_chapters(self._db, tracker, new_chapters)

        tracker.known_chapter_ids = _dump_known_ids(remote_ids)
        tracker.known_chapters = _dump_known_chapters(remote_chapters)
        tracker.last_checked_at = utcnow()
        tracker.last_error = None
        self._db.flush()
        return len(new_chapters)

    def _require_tracker(self, tracker_id: int) -> SeriesTracker:
        row = (
            self._db.query(SeriesTracker)
            .filter(
                SeriesTracker.id == tracker_id,
                SeriesTracker.user_id == self._user_id,
                SeriesTracker.profile_id == self._profile_id,
            )
            .first()
        )
        if row is None:
            raise AppError("Tracker not found", status_code=404)
        return row

    def _ensure_browsable_source(self, source: str) -> None:
        """Reject sources this caller may not act on.

        ``include_mature`` is bound to the caller's gate, not left at its
        permissive default: without it, following (or migrating onto) an 18+
        source succeeded while the gate was off — a write-side back door around
        the read-side filter, which is worse than the read leak because it
        creates a row that then has to be hidden forever after.
        """
        installed = {
            item.source_type
            for item in list_installed_connectors(
                browsable_only=True, include_mature=self._mature_enabled()
            )
        }
        if source not in installed:
            raise AppError(f"Unknown or non-browsable source '{source}'", status_code=400)

    def list_sources(self) -> list[dict[str, str]]:
        return [
            {
                "source_type": item.source_type,
                "name": item.name,
            }
            for item in list_installed_connectors(
                browsable_only=True, include_mature=self._mature_enabled()
            )
        ]


def _chapter_sort_key(chapter: ConnectorChapter) -> tuple[float, str]:
    if chapter.number is not None:
        return (chapter.number, chapter.title)
    return (10**9, chapter.title)


def get_update_service(
    db: Session,
    user_id: int | None = None,
    profile_id: int | None = None,
) -> UpdateService:
    return UpdateService(db, user_id=user_id, profile_id=profile_id)


def run_check_in_new_session(
    *, trigger: str, tracker_ids: list[int] | None = None
) -> dict[str, object]:
    """Run an update check with its own DB session (for background workers)."""
    db = SessionLocal()
    try:
        service = UpdateService(db)
        result = service.run_check(trigger=trigger, tracker_ids=tracker_ids)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
