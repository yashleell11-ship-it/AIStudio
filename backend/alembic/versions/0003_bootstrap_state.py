"""bootstrap_state: bound the empty-users-table takeover window

Revision ID: 0003_bootstrap_state
Revises: 0002_tags_per_profile
Create Date: 2026-09-04

An empty ``users`` table plus a reachable ``/auth/register`` means whoever hits
the public URL first becomes admin. ``bootstrap_state`` is a singleton row
(id=1) recording when the table was first observed empty, so the bootstrap
exception ("first registration needs no invite code") can be refused once
``Settings.bootstrap_window_minutes`` have elapsed.

The row is created lazily by the application the first time it observes an
empty users table, deleted when the first account registers, and explicitly
re-armed by ``ops/vps/deploy.sh reset-accounts`` — so this migration only
creates the (empty) table.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_bootstrap_state"
down_revision: Union[str, Sequence[str], None] = "0002_tags_per_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bootstrap_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empty_since", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("bootstrap_state")
