"""library membership and source pins

Schema foundation for per-(user, profile) library ownership.

``series`` rows are catalog facts with no owner, which is why every account
currently sees the whole catalog. This revision moves membership onto
``user_series_state`` — already keyed (user_id, profile_id, series_id) — by
adding an ``in_library`` flag, so Library / Browse / Search / statistics can all
filter through one scoped join and a brand-new account or a second profile sees
nothing another one added.

Also adds ``source_pins``: server-side pinned sources for the reworked Sources
screen, scoped the same way. ``source_id`` is the connector key, not a FK —
connectors are code, not rows. Its ``user_id`` is NOT NULL (new table, no
pre-multi-user rows) so a pin can never land in the unowned bucket.

No backfill. The database was wiped and holds 0 users and 0 series, and
inventing membership rows here would be guessing at data that does not exist.
That also keeps the revision safe against a re-run of
AuthService._claim_unowned_data: it creates no NULL-owned rows, so the
``UPDATE ... SET user_id = ? WHERE user_id IS NULL`` sweep has nothing to
collide with against uq_user_series_state.

Revision ID: f1a9c46d2e70
Revises: d4e8f1a2b3c9
Create Date: 2026-07-27 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a9c46d2e70"
down_revision: Union[str, Sequence[str], None] = "d4e8f1a2b3c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- library membership on the per-user state row -----------------------
    with op.batch_alter_table("user_series_state", schema=None) as batch_op:
        # server_default is required for a NOT NULL add on an existing table and
        # is what makes any future unowned row default to "not in my library".
        batch_op.add_column(
            sa.Column(
                "in_library",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        # Covering index for the scoped library join. The trailing series_id is
        # what makes it covering; the (user_id, profile_id, series_id) lookup is
        # already served by the index behind uq_user_series_state, so a separate
        # 3-column index would only cost writes.
        batch_op.create_index(
            "ix_user_series_state_library",
            ["user_id", "profile_id", "in_library", "series_id"],
            unique=False,
        )

    # --- server-side source pins --------------------------------------------
    op.create_table(
        "source_pins",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_source_pins_user_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["reading_profiles.id"],
            name="fk_source_pins_profile_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "profile_id", "source_id", name="uq_source_pins_user_source"
        ),
    )
    with op.batch_alter_table("source_pins", schema=None) as batch_op:
        batch_op.create_index("ix_source_pins_user_id", ["user_id"], unique=False)
        batch_op.create_index("ix_source_pins_profile_id", ["profile_id"], unique=False)
        batch_op.create_index(
            "ix_source_pins_user_sort",
            ["user_id", "profile_id", "sort_order"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("source_pins", schema=None) as batch_op:
        batch_op.drop_index("ix_source_pins_user_sort")
        batch_op.drop_index("ix_source_pins_profile_id")
        batch_op.drop_index("ix_source_pins_user_id")
    op.drop_table("source_pins")

    with op.batch_alter_table("user_series_state", schema=None) as batch_op:
        batch_op.drop_index("ix_user_series_state_library")
        batch_op.drop_column("in_library")
