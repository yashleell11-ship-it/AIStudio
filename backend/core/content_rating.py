"""Shared definition of what counts as mature (18+) content.

Kept in one place so every layer agrees on the same rule:

- the browse layer gates whole *sources* that are adult by nature
  (``SourceConnector.is_mature``), and
- the library-intelligence layer gates individual *series* by their
  stored ``content_rating`` (recommendations, similar, discovery).

Both are hidden unless the user has explicitly enabled mature content
(``Settings.mature_content_enabled``).
"""

from __future__ import annotations

#: Series ``content_rating`` values (compared case-insensitively) that denote
#: adult / 18+ content. Mirrors common source vocabularies -- e.g. MangaDex
#: uses "erotica" and "pornographic".
MATURE_CONTENT_RATINGS: frozenset[str] = frozenset(
    {
        "pornographic",
        "erotica",
        "smut",
        "hentai",
        "adult",
        "mature",
        "nsfw",
        "18+",
        "r18",
        "r-18",
    }
)


def is_mature_rating(content_rating: str | None) -> bool:
    """Whether a series ``content_rating`` denotes adult (18+) content."""
    if not content_rating:
        return False
    return content_rating.strip().lower() in MATURE_CONTENT_RATINGS
