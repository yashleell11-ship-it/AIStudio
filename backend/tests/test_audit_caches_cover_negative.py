"""AUDIT (caches shard): ``source_cover_cache`` has no negative entry.

``SourceCacheService.get_series_cover`` stores a row only when
``resize_cover`` returns bytes (source_cache_service.py:451-459). Every
"nothing to gain" outcome -- the original is already smaller than the target,
an animated cover, undecodable bytes, an HTML error page -- stores NOTHING,
so the same (series, width, fmt) goes upstream on EVERY read: a full-size
cover fetch plus a Pillow decode attempt per grid paint, on a 2-vCPU box,
for exactly the covers the feature was built to stop re-fetching.

The second test is the sharper edge: once a stored row passes the 30-day TTL
and the refreshed original no longer shrinks, the expired row is neither
refreshed nor deleted (``fetched_at`` untouched), so from then on that key is
an upstream fetch per request forever and the stale bytes are pinned in the
table with nothing to evict them but the byte budget.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from core.config import get_settings
from core.time_utils import utcnow
from database.models import SourceCoverCache
from services import source_cache_service as scs
from services.source_cache_service import SourceCacheService
from tests._fakes import FakeBrowse

SRC = "asurascans"
KEY = "some-series"


class _CoverBrowse(FakeBrowse):
    def __init__(self) -> None:
        super().__init__()
        self.cover_calls = 0

    def resolve_series_cover(self, source_id: str, series_key: str) -> tuple[str, bytes]:
        self.cover_calls += 1
        if self.down:
            raise RuntimeError("connector down")
        return "image/jpeg", b"\xff\xd8\xff-tiny-original"


def test_an_unresizable_cover_is_fetched_upstream_once_not_per_read(db_session, monkeypatch):
    monkeypatch.setattr(scs, "resize_cover", lambda data, *, width, fmt: None)
    browse = _CoverBrowse()
    svc = SourceCacheService(db_session, browse)

    for _ in range(3):
        media_type, data, served = svc.get_series_cover(SRC, KEY, width=360, fmt="jpeg")
        assert served is None and data.endswith(b"tiny-original")

    assert browse.cover_calls == 1, (
        f"connector fetched {browse.cover_calls}x for the same cover: no negative "
        f"cache entry, so a cover that cannot shrink costs an upstream fetch per paint"
    )


def test_an_expired_row_whose_refresh_cannot_shrink_is_refreshed_or_dropped(db_session, monkeypatch):
    old = utcnow() - timedelta(days=31)  # cover_cache_ttl_minutes = 30 days
    db_session.add(
        SourceCoverCache(
            source_id=SRC, series_key=KEY, width=360, fmt="jpeg",
            media_type="image/jpeg", byte_size=3, data=b"old", fetched_at=old, last_used_at=old,
        )
    )
    db_session.commit()
    monkeypatch.setattr(scs, "resize_cover", lambda data, *, width, fmt: None)
    browse = _CoverBrowse()
    svc = SourceCacheService(db_session, browse)

    svc.get_series_cover(SRC, KEY, width=360, fmt="jpeg")
    svc.get_series_cover(SRC, KEY, width=360, fmt="jpeg")

    row = db_session.execute(select(SourceCoverCache)).scalars().one_or_none()
    pinned_and_expired = row is not None and row.fetched_at == old
    assert not pinned_and_expired or browse.cover_calls == 1, (
        f"expired row still pinned at fetched_at={old} and the connector was hit "
        f"{browse.cover_calls}x: this key is now an upstream fetch per request, forever"
    )


def test_a_later_successful_downscale_clears_the_negative_entry(db_session, monkeypatch):
    """A negative entry is a cache entry, not a verdict: the day the source
    republishes a cover big enough to shrink, the row has to become an ordinary
    hit rather than keep answering with the original forever."""
    shrinks = {"yes": False}
    monkeypatch.setattr(
        scs,
        "resize_cover",
        lambda data, *, width, fmt: ("image/webp", b"small") if shrinks["yes"] else None,
    )
    browse = _CoverBrowse()
    svc = SourceCacheService(db_session, browse)

    svc.get_series_cover(SRC, KEY, width=360, fmt="jpeg")
    row = db_session.execute(select(SourceCoverCache)).scalars().one()
    assert row.resize_failed_at is not None and row.resize_failure == "no_downscale"

    shrinks["yes"] = True
    row.fetched_at = utcnow() - timedelta(days=31)  # expire it
    db_session.commit()
    media_type, data, served = svc.get_series_cover(SRC, KEY, width=360, fmt="jpeg")

    assert (media_type, data, served) == ("image/webp", b"small", 360)
    row = db_session.execute(select(SourceCoverCache)).scalars().one()
    assert row.resize_failed_at is None and row.resize_failure is None


def test_an_unresizable_original_too_big_to_store_still_skips_the_decode(
    db_session, monkeypatch
):
    """The original may exceed the per-row ceiling, in which case there is
    nothing to serve from the table and the fetch has to happen anyway. The
    marker still earns its row: it spares the Pillow decode, which is the
    expensive half on a 2-vCPU box."""
    monkeypatch.setenv("MM_COVER_CACHE_MAX_ROW_BYTES", "4")
    get_settings.cache_clear()
    decodes = {"n": 0}

    def _never_shrinks(data, *, width, fmt):
        decodes["n"] += 1
        return None

    monkeypatch.setattr(scs, "resize_cover", _never_shrinks)
    browse = _CoverBrowse()
    svc = SourceCacheService(db_session, browse)

    for _ in range(3):
        media_type, data, served = svc.get_series_cover(SRC, KEY, width=360, fmt="jpeg")
        assert served is None and data.endswith(b"tiny-original")

    row = db_session.execute(select(SourceCoverCache)).scalars().one()
    assert row.resize_failed_at is not None and row.byte_size == 0
    assert decodes["n"] == 1, f"decoded {decodes['n']}x for a key known not to shrink"
    assert browse.cover_calls == 3  # nothing stored to serve, so upstream answers
