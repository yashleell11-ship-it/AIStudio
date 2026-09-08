"""A source that rates its own work must be believed.

The 18+ rule could only ever infer maturity from genre tags, because
``connectors.models.Series`` carried no rating field. That is the right
fallback for the madara-family sites that tag "Adult" and publish nothing else
machine-readable, but it left the sources that DO rate themselves with no
signal at all.

MangaDex was the concrete leak. Its browse query asks for ``safe``,
``suggestive`` and ``erotica``, so erotica titles are in the listing; the
verdict was read to build that query and then thrown away. Every one of the
118 MangaDex rows cached in production carried neither a rating nor a genre,
on a source flagged general-audience, which meant the per-series gate had
nothing to act on for any of them.
"""

from __future__ import annotations

import json

import pytest

from connectors.mangadex.mappers import manga_to_series
from core.content_rating import hidden_by_gate, resolve_series_rating


def _manga(content_rating: str | None, *, tags: list[str] | None = None) -> dict:
    return {
        "id": "abc-123",
        "type": "manga",
        "attributes": {
            "title": {"en": "A Title"},
            "status": "ongoing",
            "contentRating": content_rating,
            # Where MangaDex really puts them, named the way it really names
            # them: on the manga's own attributes, localised rather than plain.
            "tags": [
                {
                    "id": f"tag-{index}",
                    "type": "tag",
                    "attributes": {"group": "genre", "name": {"en": tag}},
                }
                for index, tag in enumerate(tags or [])
            ],
        },
        "relationships": [],
    }


class TestTheMapperReportsIt:
    @pytest.mark.parametrize(
        "declared,expected",
        [
            ("erotica", "mature"),
            ("pornographic", "mature"),
            ("safe", "safe"),
            # Not adult: mildly racy is still visible, and only MATURE hides.
            ("suggestive", "safe"),
        ],
    )
    def test_mangadex_own_verdict_reaches_the_rule(self, declared, expected):
        series = manga_to_series(_manga(declared))

        assert series.content_rating == declared
        assert resolve_series_rating(series.content_rating, list(series.genres)) == (
            expected
        )

    def test_an_erotica_title_is_hidden_from_a_shut_gate(self):
        """The leak itself: a general-audience source listing erotica."""
        series = manga_to_series(_manga("erotica"))
        rating = resolve_series_rating(series.content_rating, list(series.genres))

        assert hidden_by_gate(rating, gate_open=False) is True
        assert hidden_by_gate(rating, gate_open=True) is False

    def test_a_manga_with_no_verdict_still_falls_back_to_its_tags(self):
        series = manga_to_series(_manga(None, tags=["Action", "Smut"]))

        assert series.content_rating is None
        assert resolve_series_rating(series.content_rating, list(series.genres)) == (
            "mature"
        )

    def test_normalised_so_the_stored_value_round_trips(self):
        assert manga_to_series(_manga("  EROTICA ")).content_rating == "erotica"


class TestTheCacheStoresIt:
    def test_a_declared_rating_beats_the_genre_sweep(self, db_session):
        """A source's own verdict wins over an inference from its tags.

        Not merely a preference: a title tagged "Romance" and rated erotica
        would otherwise be stored unrated, which is exactly the row the gate
        needs to catch.
        """
        from database.models import SourceSeriesCache
        from services.source_cache_service import SourceCacheService
        from tests._fakes import FakeBrowse

        svc = SourceCacheService(db_session, FakeBrowse())
        svc._write_through_listing(
            "mangadex",
            [
                {
                    "id": "s1",
                    "title": "Rated By The Source",
                    "genres": ["Romance"],
                    "content_rating": "erotica",
                }
            ],
        )
        db_session.commit()

        row = db_session.get(SourceSeriesCache, ("mangadex", "s1"))
        assert row is not None
        assert row.content_rating == "erotica"

    def test_the_genre_sweep_still_runs_for_a_source_that_rates_nothing(
        self, db_session
    ):
        from database.models import SourceSeriesCache
        from services.source_cache_service import SourceCacheService
        from tests._fakes import FakeBrowse

        svc = SourceCacheService(db_session, FakeBrowse())
        svc._write_through_listing(
            "somemadara",
            [{"id": "s2", "title": "Tagged Only", "genres": ["Action", "Smut"]}],
        )
        db_session.commit()

        row = db_session.get(SourceSeriesCache, ("somemadara", "s2"))
        assert row is not None
        assert row.content_rating == "smut"

    def test_an_empty_declared_rating_does_not_erase_the_tag_signal(
        self, db_session
    ):
        from database.models import SourceSeriesCache
        from services.source_cache_service import SourceCacheService
        from tests._fakes import FakeBrowse

        svc = SourceCacheService(db_session, FakeBrowse())
        svc._write_through_listing(
            "somesource",
            [
                {
                    "id": "s3",
                    "title": "Blank Verdict",
                    "genres": ["Smut"],
                    "content_rating": "   ",
                }
            ],
        )
        db_session.commit()

        row = db_session.get(SourceSeriesCache, ("somesource", "s3"))
        assert row is not None
        assert row.content_rating == "smut"


def test_the_serialized_listing_carries_the_rating_for_the_gate_to_read():
    """``serialized_series_rating`` reads ``content_rating`` off the dict, so a
    serializer that drops the field silently disarms every cached serve."""
    from connectors.models import Series
    from core.content_rating import serialized_series_rating
    from services.browse_service import _serialize_series

    item = _serialize_series(
        Series(id="x", title="T", content_rating="erotica"), "mangadex"
    )

    assert item["content_rating"] == "erotica"
    assert serialized_series_rating(item) == "mature"
    # And it survives the JSON round trip the browse cache stores it through.
    assert serialized_series_rating(json.loads(json.dumps(item))) == "mature"


class TestTheTagsAreReadAtAll:
    """The genre half of the same blindness.

    ``_tag_genres`` looked for tags in the relationship map, under a plain
    string name. MangaDex carries them on ``attributes.tags`` and localises
    every name, so the read matched nothing on any real payload and every
    MangaDex row cached in production had an empty genre tuple -- a hole in
    the browse UI as well as in the rule.
    """

    def test_tags_on_the_manga_attributes_are_found(self):
        series = manga_to_series(_manga("safe", tags=["Action", "Romance"]))

        assert series.genres == ("Action", "Romance")

    def test_a_localised_name_is_unwrapped(self):
        payload = _manga("safe")
        payload["attributes"]["tags"] = [
            {"attributes": {"group": "genre", "name": {"ja": "\u30a2\u30af\u30b7\u30e7\u30f3"}}}
        ]

        # No English name: any translation beats dropping the tag entirely.
        assert manga_to_series(payload).genres != ()

    def test_format_tags_are_left_out(self):
        payload = _manga("safe")
        payload["attributes"]["tags"] = [
            {"attributes": {"group": "format", "name": {"en": "Long Strip"}}},
            {"attributes": {"group": "genre", "name": {"en": "Action"}}},
            {"attributes": {"group": "content", "name": {"en": "Gore"}}},
        ]

        genres = manga_to_series(payload).genres
        assert "Long Strip" not in genres
        assert set(genres) == {"Action", "Gore"}

    def test_a_tag_repeated_across_shapes_appears_once(self):
        payload = _manga("safe", tags=["Action"])
        payload["relationships"] = [
            {"type": "tag", "attributes": {"group": "genre", "name": "Action"}}
        ]

        assert manga_to_series(payload).genres == ("Action",)
