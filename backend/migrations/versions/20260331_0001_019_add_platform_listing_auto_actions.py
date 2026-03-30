"""Add auto-action and approval columns to platform_listings.

Revision ID: 019
Revises: 018
Create Date: 2026-03-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON


# revision identifiers
revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if not _has_table("platform_listings"):
        return

    # Add idempotency_key
    if not _has_column("platform_listings", "idempotency_key"):
        op.add_column(
            "platform_listings",
            sa.Column("idempotency_key", sa.String(255), nullable=True),
        )
        op.create_index(
            "ix_platform_listings_idempotency_key",
            "platform_listings",
            ["idempotency_key"],
            unique=False,
        )

    # Add approval_required
    if not _has_column("platform_listings", "approval_required"):
        op.add_column(
            "platform_listings",
            sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.create_index(
            "ix_platform_listings_approval_required",
            "platform_listings",
            ["approval_required"],
            unique=False,
        )

    # Add approval_reason
    if not _has_column("platform_listings", "approval_reason"):
        op.add_column(
            "platform_listings",
            sa.Column("approval_reason", sa.Text(), nullable=True),
        )

    # Add auto_action_metadata
    if not _has_column("platform_listings", "auto_action_metadata"):
        op.add_column(
            "platform_listings",
            sa.Column("auto_action_metadata", JSON, nullable=True),
        )

    # Add approved_at
    if not _has_column("platform_listings", "approved_at"):
        op.add_column(
            "platform_listings",
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        )

    # Add approved_by
    if not _has_column("platform_listings", "approved_by"):
        op.add_column(
            "platform_listings",
            sa.Column("approved_by", sa.String(100), nullable=True),
        )

    # Add rejected_at
    if not _has_column("platform_listings", "rejected_at"):
        op.add_column(
            "platform_listings",
            sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        )

    # Add rejected_by
    if not _has_column("platform_listings", "rejected_by"):
        op.add_column(
            "platform_listings",
            sa.Column("rejected_by", sa.String(100), nullable=True),
        )

    # Add rejection_reason
    if not _has_column("platform_listings", "rejection_reason"):
        op.add_column(
            "platform_listings",
            sa.Column("rejection_reason", sa.Text(), nullable=True),
        )

    # Add last_auto_action_at
    if not _has_column("platform_listings", "last_auto_action_at"):
        op.add_column(
            "platform_listings",
            sa.Column("last_auto_action_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    if not _has_table("platform_listings"):
        return

    # Drop columns in reverse order
    if _has_column("platform_listings", "last_auto_action_at"):
        op.drop_column("platform_listings", "last_auto_action_at")

    if _has_column("platform_listings", "rejection_reason"):
        op.drop_column("platform_listings", "rejection_reason")

    if _has_column("platform_listings", "rejected_by"):
        op.drop_column("platform_listings", "rejected_by")

    if _has_column("platform_listings", "rejected_at"):
        op.drop_column("platform_listings", "rejected_at")

    if _has_column("platform_listings", "approved_by"):
        op.drop_column("platform_listings", "approved_by")

    if _has_column("platform_listings", "approved_at"):
        op.drop_column("platform_listings", "approved_at")

    if _has_column("platform_listings", "auto_action_metadata"):
        op.drop_column("platform_listings", "auto_action_metadata")

    if _has_column("platform_listings", "approval_reason"):
        op.drop_column("platform_listings", "approval_reason")

    if _has_column("platform_listings", "approval_required"):
        op.drop_index("ix_platform_listings_approval_required", table_name="platform_listings")
        op.drop_column("platform_listings", "approval_required")

    if _has_column("platform_listings", "idempotency_key"):
        op.drop_index("ix_platform_listings_idempotency_key", table_name="platform_listings")
        op.drop_column("platform_listings", "idempotency_key")
