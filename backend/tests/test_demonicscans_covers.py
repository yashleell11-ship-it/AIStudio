"""DemonicScans cover parsing, ID decoding, and image-proxy allowlist."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from connectors.demonicscans.connector import DemonicScansConnector
from connectors.demonicscans.mappers import parse_series_cards, parse_series_detail
from connectors.ids import fully_unquote
from services.browse_service import BrowseService, _serialize_series
from connectors.models import Series

FIXTURES = Path(__file__).parent / "fixtures" / "demonicscans"


def test_fully_unquote_decodes_double_encoding() -> None:
    assert fully_unquote("WORTHLESS-PROFESSION%253A-DRAGON-TAMER") == (
        "WORTHLESS-PROFESSION:-DRAGON-TAMER"
    )
    assert fully_unquote("I%2527m-Back%2521") == "I'm-Back!"
    assert fully_unquote("plain-slug") == "plain-slug"


def test_parse_series_cards_uses_title_attr_and_decodes_ids() -> None:
    html = (FIXTURES / "browse_latest.html").read_text(encoding="utf-8")
    cards = parse_series_cards(html)
    by_id = {card.id: card for card in cards}

    assert "Mr-Devourer,-Please-Act-Like-a-Final-Boss" in by_id
    devourer = by_id["Mr-Devourer,-Please-Act-Like-a-Final-Boss"]
    assert devourer.title == "Mr Devourer, Please Act Like a Final Boss"
    assert devourer.cover_url and "Mr Devourer" in devourer.cover_url
    assert "%25" not in devourer.id
    assert "%25" not in devourer.title

    worthless = by_id["WORTHLESS-PROFESSION:-DRAGON-TAMER"]
    assert worthless.title == "WORTHLESS PROFESSION: DRAGON TAMER"
    assert worthless.cover_url and "WORTHLESS" in worthless.cover_url

    crazy = by_id["Return-of-the-Crazy-Demon"]
    assert crazy.cover_url and "Mad Demon" in crazy.cover_url


def test_parse_series_cards_does_not_borrow_next_cover() -> None:
    html = (FIXTURES / "browse_latest.html").read_text(encoding="utf-8")
    cards = parse_series_cards(html)
    by_id = {card.id: card for card in cards}
    assert "WORTHLESS" in (by_id["WORTHLESS-PROFESSION:-DRAGON-TAMER"].cover_url or "")
    assert "Mad Demon" in (by_id["Return-of-the-Crazy-Demon"].cover_url or "")


def test_parse_series_detail_uses_og_image() -> None:
    html = (FIXTURES / "series_detail.html").read_text(encoding="utf-8")
    series = parse_series_detail(html, "Tales-of-Demons-and-Gods")
    assert series is not None
    assert series.title == "Tales of Demons and Gods"
    assert series.cover_url == (
        "https://readermc.org/images/thumbnails/Tales of Demons and Gods.webp"
    )


def test_serialize_cover_url_quotes_decoded_id_once() -> None:
    series = Series(
        id="WORTHLESS-PROFESSION:-DRAGON-TAMER",
        title="WORTHLESS PROFESSION: DRAGON TAMER",
        cover_url="https://readermc.org/images/thumbnails/x.webp",
    )
    payload = _serialize_series(series, "demonicscans")
    cover = str(payload["cover_url"])
    assert cover == (
        "/sources/demonicscans/series/WORTHLESS-PROFESSION%3A-DRAGON-TAMER/cover"
    )
    assert "%253A" not in cover
    assert "%2525" not in cover


def test_demonicscans_allowlist_includes_readermc() -> None:
    connector = DemonicScansConnector()
    assert "readermc.org" in connector.allowed_image_hosts
    assert connector.image_fetch_headers()["Referer"] == "https://demonicscans.org/"


def test_resolve_series_cover_fetches_readermc(monkeypatch: pytest.MonkeyPatch) -> None:
    connector = DemonicScansConnector()
    series = Series(
        id="Return-of-the-Crazy-Demon",
        title="Return of the Crazy Demon",
        cover_url="https://readermc.org/images/thumbnails/Return of the Mad Demon.webp",
    )
    service = BrowseService()
    monkeypatch.setattr(service, "_get_connector", lambda _sid: connector)
    monkeypatch.setattr(connector, "get_series", lambda _sid: series)

    mock_response = MagicMock()
    mock_response.is_redirect = False
    mock_response.headers = {"content-type": "image/webp"}
    mock_response.content = b"webp-bytes"
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.get", return_value=mock_response) as mock_get:
        media_type, data = service.resolve_series_cover(
            "demonicscans", "Return-of-the-Crazy-Demon"
        )

    assert media_type == "image/webp"
    assert data == b"webp-bytes"
    mock_get.assert_called_once()
    assert mock_get.call_args.kwargs["headers"]["Referer"] == "https://demonicscans.org/"
