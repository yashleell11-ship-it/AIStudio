"""tracker maturity and source migration

Two features land on ``series_trackers`` at once because they need the same
columns for the same reason: a followed *remote* series has no local ``Series``
row to read facts off. ``local_series_id`` is never written by any code path, and
``connectors.models.Series`` carries neither a rating nor stable ids, so the
tracker row itself has to carry what the server needs to know about it.

Maturity (``content_rating``, ``mature_override``):
  The 18+ gate could not hide a followed 18+ series because nothing recorded
  that it was one. ``content_rating`` is captured at follow time from the
  connector's genres; ``mature_override`` is the user's explicit verdict and
  wins over everything, which is the only signal that works for the many dead
  connectors where no metadata will ever arrive again. Both nullable: NULL is
  "no signal", which resolves to *unknown* (surfaced and badged) rather than to
  safe -- see ``core.content_rating.resolve_tracker_rating``.

Migration (``known_chapters``, ``migrated_from_*``):
  Repointing a follow at another source remaps reading progress by chapter
  NUMBER, but ``known_chapter_ids`` stores ids only. ``known_chapters`` keeps
  ``[{"id", "number"}]`` alongside it so a migration off a source that has since
  gone dark can still map -- the whole reason the feature exists.
  ``known_chapter_ids`` is deliberately left in place: the update engine's diff
  is a pure id-set difference and is not worth destabilising here.

Backfill: every existing tracker whose ``source`` is a mature connector is
stamped ``content_rating = 'mature'``, so the first release hides the obvious
cases (toonily, nhentai, hentai20, …) with no user action. Trackers on
general-purpose sources are left NULL/unknown on purpose -- guessing "adult"
there would blank follows the owner did not ask to hide, and he can mark those
individually via ``mature_override``.

Revision ID: a7c3e51b90d4
Revises: f1a9c46d2e70
Create Date: 2026-07-27 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7c3e51b90d4"
down_revision: Union[str, Sequence[str], None] = "f1a9c46d2e70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _mature_source_types() -> list[str]:
    """Connector keys flagged adult in the registry.

    Read from the registry rather than hard-coded: the connector list changes
    far more often than migrations do, and a stale literal list here would
    silently under-hide. Import is local so a registry import failure cannot
    break unrelated migrations at module load.
    """
    try:
        from connectors.registry import list_installed_connectors
    except Exception:  # pragma: no cover - registry unavailable in this context
        return []
    return [
        descriptor.source_type
        for descriptor in list_installed_connectors(include_mature=True)
        if descriptor.mature
    ]


def upgrade() -> None:
    with op.batch_alter_table("series_trackers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("known_chapters", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("content_rating", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(sa.Column("mature_override", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("migrated_from_source", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("migrated_from_series_id", sa.String(length=128), nullable=True)
        )
        batch_op.add_column(sa.Column("migrated_at", sa.DateTime(), nullable=True))
        # The gate filters trackers by resolved rating on every /updates/trackers
        # read, so the rating column carries the same index weight as track_kind.
        batch_op.create_index(
            "ix_series_trackers_content_rating", ["content_rating"], unique=False
        )

    mature_sources = _mature_source_types()
    if mature_sources:
        op.execute(
            sa.text(
                "UPDATE series_trackers SET content_rating = 'mature' "
                "WHERE content_rating IS NULL AND source IN :sources"
            ).bindparams(sa.bindparam("sources", value=mature_sources, expanding=True))
        )


def downgrade() -> None:
    with op.batch_alter_table("series_trackers", schema=None) as batch_op:
        batch_op.drop_index("ix_series_trackers_content_rating")
        batch_op.drop_column("migrated_at")
        batch_op.drop_column("migrated_from_series_id")
        batch_op.drop_column("migrated_from_source")
        batch_op.drop_column("mature_override")
        batch_op.drop_column("content_rating")
        batch_op.drop_column("known_chapters")
