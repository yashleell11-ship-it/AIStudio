"""Per-source spread and pacing for bulk download runs."""

from __future__ import annotations

from dataclasses import dataclass

from services.download_scheduling import (
    SourcePacer,
    connector_min_interval,
    select_round_robin,
)


@dataclass
class Row:
    id: int
    source: str


def rows(*spec: tuple[int, str]) -> list[Row]:
    return [Row(id=i, source=s) for i, s in spec]


class TestSelectRoundRobin:
    def test_spreads_workers_across_sources_instead_of_one_host(self):
        # The old behaviour: 100 queued chapters from one source took every
        # worker, leaving every other source idle and hammering one site.
        pending = rows(
            (1, "asura"), (2, "asura"), (3, "asura"), (4, "asura"),
            (5, "toonily"), (6, "toonily"),
            (7, "manga18x"),
        )

        picked = select_round_robin(pending, available=4, per_source_limit=2)

        assert picked == [1, 5, 7, 2]

    def test_preserves_queue_order_within_a_source(self):
        pending = rows((10, "a"), (11, "a"), (12, "a"))

        picked = select_round_robin(pending, available=2, per_source_limit=5)

        # Priority still decides which chapter of a source goes next; only how
        # many of one source run at once changed.
        assert picked == [10, 11]

    def test_respects_the_per_source_limit(self):
        pending = rows((1, "a"), (2, "a"), (3, "a"), (4, "a"))

        picked = select_round_robin(pending, available=10, per_source_limit=2)

        assert picked == [1, 2]

    def test_counts_already_running_downloads_against_the_limit(self):
        pending = rows((1, "a"), (2, "b"))

        picked = select_round_robin(
            pending, available=4, per_source_limit=2, in_flight=["a", "a"]
        )

        # Without this the cap would not hold: every dispatch pass would top
        # each source back up to the limit on top of what is already running.
        assert picked == [2]

    def test_a_saturated_source_does_not_block_the_ones_behind_it(self):
        pending = rows((1, "busy"), (2, "busy"), (3, "idle"))

        picked = select_round_robin(
            pending, available=3, per_source_limit=1, in_flight=["busy"]
        )

        assert picked == [3]

    def test_returns_nothing_when_no_workers_are_free(self):
        assert select_round_robin(rows((1, "a")), available=0) == []

    def test_returns_nothing_rather_than_looping_forever_when_all_capped(self):
        pending = rows((1, "a"), (2, "a"))

        picked = select_round_robin(
            pending, available=5, per_source_limit=1, in_flight=["a"]
        )

        assert picked == []

    def test_single_source_still_uses_its_full_allowance(self):
        pending = rows((1, "solo"), (2, "solo"), (3, "solo"))

        picked = select_round_robin(pending, available=5, per_source_limit=3)

        # Spreading must not mean throttling a lone source below its limit.
        assert picked == [1, 2, 3]


class TestSourcePacer:
    def test_first_request_to_a_source_does_not_wait(self):
        pacer = SourcePacer()

        assert pacer.wait("asura", 0.05) == 0.0

    def test_second_request_to_the_same_source_waits(self):
        pacer = SourcePacer()
        pacer.wait("asura", 0.05)

        assert pacer.wait("asura", 0.05) > 0.0

    def test_a_different_source_is_not_made_to_wait(self):
        pacer = SourcePacer()
        pacer.wait("asura", 0.5)

        # Pacing one site must never stall a worker on another - that is the
        # whole point of downloading sources in parallel.
        assert pacer.wait("toonily", 0.5) == 0.0

    def test_zero_interval_disables_pacing(self):
        pacer = SourcePacer()
        pacer.wait("a", 0.0)

        assert pacer.wait("a", 0.0) == 0.0


class TestConnectorMinInterval:
    def test_reads_the_interval_the_connector_already_declares(self):
        class Client:
            _min_interval = 1.25

        class Connector:
            _client = Client()

        # The per-site values were tuned once for metadata calls; the image
        # path spends the same budget rather than a second invented one.
        assert connector_min_interval(Connector()) == 1.25

    def test_falls_back_when_a_connector_declares_none(self):
        class Connector:
            pass

        assert connector_min_interval(Connector(), default=0.21) == 0.21

    def test_ignores_a_nonsense_interval(self):
        class Client:
            _min_interval = 0

        class Connector:
            _client = Client()

        assert connector_min_interval(Connector(), default=0.21) == 0.21
