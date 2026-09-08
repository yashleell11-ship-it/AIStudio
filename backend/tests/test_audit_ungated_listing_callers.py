"""``apply_gate=False`` has exactly one legitimate caller.

``BrowseService.list_series(apply_gate=False)`` returns a catalog page without
the per-row 18+ filter. It exists so ``SourceCacheService`` can store a whole
page in a table every profile reads and apply each caller's own gate on the
way out, which is the only way a shared cache can be correct in both
directions: gating before the store made the rows a caller sees depend on
whichever profile happened to warm the row.

That makes it the one deliberate way to get an ungated listing in this
codebase, which is worth a census rather than a comment. A second caller is
almost certainly a leak, and would be easy to add without noticing -- the
keyword reads like a performance flag.
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

#: Where an ungated listing may legitimately be asked for.
ALLOWED = {
    # Stores the page, then gates it per caller in `_gate_listing`.
    "services/source_cache_service.py",
}

#: Directories that hold shipped code or the tests that pin it.
_ROOTS = ("services", "routes", "core", "connectors", "utils", "tests")


def _sources() -> list[Path]:
    files: list[Path] = []
    for root in _ROOTS:
        files.extend((BACKEND / root).rglob("*.py"))
    return files


def _passes_apply_gate_false(path: Path) -> bool:
    """True when this file CALLS something with ``apply_gate=False``.

    Parsed rather than grepped: the keyword is named in several docstrings
    explaining why it exists, and a census that counts prose would either fail
    on its own explanation or be loosened until it stopped checking anything.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if (
                keyword.arg == "apply_gate"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is False
            ):
                return True
    return False


def test_only_the_cache_asks_for_an_ungated_listing() -> None:
    offenders = sorted(
        str(path.relative_to(BACKEND))
        for path in _sources()
        if _passes_apply_gate_false(path)
        and str(path.relative_to(BACKEND)) not in ALLOWED
    )

    assert offenders == [], (
        "apply_gate=False bypasses the per-row 18+ filter. A new caller must "
        "apply the rating rule itself before serving, the way "
        "SourceCacheService._gate_listing does, and be added to ALLOWED here "
        f"with a reason. Found: {offenders}"
    )


def test_the_census_is_actually_looking_at_something() -> None:
    """A census that matches nothing passes for the wrong reason."""
    hits = [p for p in _sources() if _passes_apply_gate_false(p)]

    assert hits, "the pattern found no callers at all; has the keyword been renamed?"
    assert any("source_cache_service" in str(p) for p in hits)


def test_the_gate_is_on_by_default() -> None:
    """Every caller that does not opt out gets the filter."""
    import inspect

    from services.browse_service import BrowseService

    default = inspect.signature(BrowseService.list_series).parameters["apply_gate"]
    assert default.default is True
