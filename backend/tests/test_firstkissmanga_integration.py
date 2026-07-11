"""Live integration smoke test for the 1st Kiss Manga connector."""

from __future__ import annotations

import pytest

from connectors.firstkissmanga.connector import FirstKissMangaConnector
from connectors.http.client import ConnectorHttpError

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def connector() -> FirstKissMangaConnector:
    return FirstKissMangaConnector()


def _skip_on_network(exc: Exception) -> None:
    pytest.skip(f"1stkissmanga.io unreachable/changed: {exc!r}")


def test_live_browse_returns_series(connector: FirstKissMangaConnector):
    try:
        listing = connector.get_series_list(1)
    except (ConnectorHttpError, OSError) as exc:
        _skip_on_network(exc)
    if not listing.items:
        pytest.skip("1stkissmanga.io returned an empty listing (site may be parked/down)")
    assert listing.items[0].title
    assert listing.items[0].id
