"""Generic chapter-title normalization shared by source connectors."""

from __future__ import annotations

import re

# Leading episode/arc counters such as "47. " or "3) " (but never decimals
# like "1.5 Interlude", where a digit follows the separator).
_NUMERIC_PREFIX = re.compile(r"^\d{1,4}\s*[.)]\s*(?!\d)")


def normalize_chapter_title(title: str | None) -> str | None:
    """Collapse whitespace and drop a leading numeric episode/arc prefix.

    Aggregator sources emit titles like ``"47. The Culprit (7)"`` or
    ``"48.Heavenly Demon Inauguration (1)"`` where the number is the source
    novel's episode counter — not the chapter number, which arrives in a
    separate field. Displaying it alongside the real chapter number reads as a
    conflicting chapter number, so it is stripped here while the chapter's
    ``number`` field remains the single source of ordering.

    Returns ``None`` when nothing displayable remains so callers can apply
    their usual "Chapter N" fallback.
    """
    if not title:
        return None
    text = re.sub(r"\s+", " ", str(title)).strip()
    stripped = _NUMERIC_PREFIX.sub("", text, count=1).strip()
    # Never strip a title down to nothing (e.g. a literal "3." title).
    if stripped:
        text = stripped
    return text or None
