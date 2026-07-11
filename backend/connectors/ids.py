"""Shared ID normalization for source connectors."""

from __future__ import annotations

from urllib.parse import unquote


def fully_unquote(value: str) -> str:
    """Decode percent-encoding until stable.

    Some aggregator sites emit double-encoded path segments (``%253A`` for
    ``:``). A single ``unquote`` leaves residual ``%3A`` in titles/IDs and
    causes a second encode when building cover proxy URLs.
    """
    text = value
    for _ in range(8):
        decoded = unquote(text)
        if decoded == text:
            return text
        text = decoded
    return text
