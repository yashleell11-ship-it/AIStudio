"""source health

Records whether each source connector is answering.

Roughly 100 of the ~151 installed connectors are dead, and nothing recorded it:
the owner learned a source had died only when a followed series quietly stopped
updating. This adds the one table that makes that visible -- last success, last
failure and its message, the consecutive-failure streak, and when the source was
last probed.

The table is GLOBAL (no user_id / profile_id) on purpose. Reachability is a
property of the site, not of the account that happened to search while it was
down; scoping it per user would make every account rediscover the same dead
connectors, and a new profile would start from "unknown" for all 151. The
mature-content gate is still honoured at read time -- the endpoints iterate the
caller's gated descriptor list, never this table -- so a mature source's health
does not leak to a profile that cannot see the source.

``source_id`` is the connector key, not a foreign key: connectors are code, not
rows, and a health row must survive a connector being temporarily unregistered.
It is UNIQUE because this is current state, not an event log.

No backfill. Health is an observation; inventing "ok" or "dead" for 151
connectors nobody has probed yet would be a guess, and an absent row already has
a correct meaning ("never checked").

Revision ID: e6d1c73f9a24
Revises: b8f52d1c47ae
Create Date: 2026-07-28 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e6d1c73f9a24"
down_revision: Union[str, Sequence[str], None] = "b8f52d1c47ae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "source_health",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("last_ok_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        # server_default so a row inserted by raw SQL (backup/restore, manual
        # fixups) can never land a NULL streak that the demotion arithmetic
        # would then have to defend against.
        sa.Column(
            "consecutive_failures", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", name="uq_source_health_source_id"),
    )
    with op.batch_alter_table("source_health", schema=None) as batch_op:
        batch_op.create_index(
            "ix_source_health_consecutive_failures",
            ["consecutive_failures"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("source_health", schema=None) as batch_op:
        batch_op.drop_index("ix_source_health_consecutive_failures")
    op.drop_table("source_health")
