"""download profile scope

Adds ``downloads.profile_id`` so a queued download records WHICH reading
profile asked for it, not just which account.

Why it is needed: library membership is per-(user, profile) — it lives on
``user_series_state.in_library`` — and the download worker adds the imported
series to the downloader's library when a chapter completes. The worker has no
request context, so it reads ownership off the ``Download`` row; with only
``user_id`` there it could not name a profile, the membership row landed in the
unscoped ``(NULL, NULL)`` bucket, and the freshly downloaded series was
invisible in every profile's library with no way to surface it.

Shape mirrors ``series_trackers.profile_id``: nullable, indexed, FK to
``reading_profiles`` ON DELETE CASCADE.

NO BACKFILL. Unlike d4e8f1a2b3c9 — which back-attributed pre-existing scoped
rows to each owner's oldest profile because those rows *were* profile-owned data
that simply predated the column — a download predates the notion of an
initiating profile entirely. Picking "the oldest profile" here would assert that
a specific person downloaded something when the database has never held that
fact, and would drop a stranger's series into a profile's library (a child
profile included). Legacy rows keep ``profile_id NULL``, and the worker treats
NULL as the account's unscoped bucket rather than guessing.

``download_queue.download_id`` gains ON DELETE CASCADE in the same revision.
That is not cosmetic: with foreign keys enforced (``PRAGMA foreign_keys=ON``,
set on every connection in ``database.session``), deleting a profile now
cascades away its ``downloads`` rows, and each surviving ``download_queue`` row
would be left with a dangling NOT NULL ``download_id`` — SQLite aborts the whole
profile delete with "FOREIGN KEY constraint failed". The queue row owns nothing
independently of its download, so it follows it.

Revision ID: b8f52d1c47ae
Revises: a7c3e51b90d4
Create Date: 2026-07-28 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8f52d1c47ae"
down_revision: Union[str, Sequence[str], None] = "a7c3e51b90d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("downloads", schema=None) as batch_op:
        batch_op.add_column(sa.Column("profile_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_downloads_profile_id", ["profile_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_downloads_profile_id",
            "reading_profiles",
            ["profile_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # Recreate the queue -> download FK with ON DELETE CASCADE. SQLite cannot
    # alter a constraint in place, so batch mode rebuilds the table; the
    # existing constraint is unnamed in the baseline schema, hence naming it
    # here via naming_convention rather than dropping it by name.
    with op.batch_alter_table(
        "download_queue",
        schema=None,
        naming_convention={"fk": "fk_%(table_name)s_%(column_0_name)s"},
    ) as batch_op:
        batch_op.drop_constraint("fk_download_queue_download_id", type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_download_queue_download_id",
            "downloads",
            ["download_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table(
        "download_queue",
        schema=None,
        naming_convention={"fk": "fk_%(table_name)s_%(column_0_name)s"},
    ) as batch_op:
        batch_op.drop_constraint("fk_download_queue_download_id", type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_download_queue_download_id", "downloads", ["download_id"], ["id"]
        )

    with op.batch_alter_table("downloads", schema=None) as batch_op:
        batch_op.drop_constraint("fk_downloads_profile_id", type_="foreignkey")
        batch_op.drop_index("ix_downloads_profile_id")
        batch_op.drop_column("profile_id")
