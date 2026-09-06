"""AUDIT (migrations shard) — autogenerate must not propose dropping the FTS5 index.

``chapter_ocr_fts`` is created by raw DDL in 0001 (SQLAlchemy has no FTS5
construct) and drags four shadow tables with it (``_data``, ``_idx``,
``_docsize``, ``_config``). None of the five is in ``Base.metadata``, so
without a name filter in ``alembic/env.py`` a plain ``alembic revision
--autogenerate`` against a database at head writes a revision whose
``upgrade()`` drops all of them — the OCR search index, gone on the next boot
if anyone applies what the tool suggested. Reproduced: five ``remove_table``
diffs at head before the filter existed.

The check drives the real ``revision --autogenerate`` through env.py rather
than ``compare_metadata`` with hand-picked options, so it is env.py's own
filter that is on trial. ``process_revision_directives`` empties the
directive list, so no revision file is ever written into ``alembic/versions``.
The second test is the negative control: a filter wide enough to hide every
unknown table would satisfy the first one while leaving autogenerate useless.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

import database.session as dbs


def _cfg(db_path: Path) -> Config:
    root = Path(dbs.__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    cfg.attributes["db_url"] = f"sqlite:///{db_path}"
    return cfg


def _autogenerate_diffs(cfg: Config) -> list[tuple[str, str]]:
    """What ``alembic revision --autogenerate`` would put in ``upgrade()``."""
    captured = {}

    def capture(context, revision, directives):  # noqa: ARG001
        captured["ops"] = directives[0].upgrade_ops
        # Keep the probe from writing a revision file into the real tree.
        directives[:] = []

    command.revision(
        cfg,
        message="audit probe",
        autogenerate=True,
        process_revision_directives=capture,
    )
    return [
        (d[0], getattr(d[1], "name", d[1])) for d in captured["ops"].as_diffs()
    ]


def test_autogenerate_against_head_reports_no_diff(tmp_path):
    cfg = _cfg(tmp_path / "head.db")
    command.upgrade(cfg, "head")

    assert _autogenerate_diffs(cfg) == []


def test_autogenerate_still_reports_a_table_the_filter_does_not_cover(tmp_path):
    """Negative control: a filter that hid everything would pass the test above.

    The FTS names are excluded by name, so anything else the database has and
    the metadata does not must still show up — otherwise autogenerate has been
    silenced rather than corrected.
    """
    db = tmp_path / "head.db"
    cfg = _cfg(db)
    command.upgrade(cfg, "head")
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE zz_not_in_metadata (id INTEGER PRIMARY KEY)")
    c.commit()
    c.close()

    assert _autogenerate_diffs(cfg) == [("remove_table", "zz_not_in_metadata")]
