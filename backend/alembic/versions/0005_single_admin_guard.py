"""single_admin_guard: at most one is_admin=1 row, enforced by the database

Revision ID: 0005_single_admin_guard
Revises: 0004_source_browse_cache
Create Date: 2026-09-04

The bootstrap claim ("first account in an empty users table becomes admin")
was a check-then-act race: concurrent POST /auth/register requests could each
observe an empty table and every one of them committed as an admin — a
verified privilege escalation. The application now serializes the claim
(``AuthService.register`` runs count → INSERT → consume ``bootstrap_state``
inside one ``BEGIN IMMEDIATE`` transaction); this migration adds the DB-level
backstop: a partial unique index allowing at most ONE ``is_admin=1`` row, so
any future lost race fails with an IntegrityError instead of silently minting
a second owner.

This encodes a deliberate product decision: the household model has exactly
one admin/owner (there is no admin-promotion path anywhere in the code, and
``create-owner`` funnels through the same ``register`` bootstrap). If
co-admins ever become a feature, drop this index in that migration.

A database that was already exploited may hold several admin rows, which
would make CREATE UNIQUE INDEX fail — so extras are demoted first, keeping
the earliest (lowest id) admin, i.e. the account that legitimately won the
original bootstrap.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_single_admin_guard"
down_revision: Union[str, Sequence[str], None] = "0004_source_browse_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Demote every admin but the earliest one, so the index can be created on
    # a database that raced before this guard existed. On a healthy database
    # this touches nothing.
    op.execute(
        sa.text(
            "UPDATE users SET is_admin = 0 "
            "WHERE is_admin = 1 "
            "AND id != (SELECT MIN(id) FROM users WHERE is_admin = 1)"
        )
    )
    op.create_index(
        "uq_users_single_admin",
        "users",
        ["is_admin"],
        unique=True,
        sqlite_where=sa.text("is_admin = 1"),
    )


def downgrade() -> None:
    op.drop_index("uq_users_single_admin", table_name="users")
