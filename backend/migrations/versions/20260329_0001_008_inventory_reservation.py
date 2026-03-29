"""Migration: Add inventory reservation support.

Revision ID: 008_inventory_reservation
Revises: 007_erp_lite_procurement
Create Date: 2026-03-29 00:01:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "008_inventory_reservation"
down_revision: Union[str, None] = "007_erp_lite_procurement"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table_name)


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    # Create inventory_reservations table
    if not _has_table("inventory_reservations"):
        op.create_table(
            "inventory_reservations",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("reference_type", sa.String(length=50), nullable=False),
            sa.Column("reference_id", sa.String(length=100), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_inventory_reservations_variant_id", "inventory_reservations", ["variant_id"])
        op.create_index("idx_inventory_reservations_reference_id", "inventory_reservations", ["reference_id"])
        op.create_index(
            "idx_inventory_reservations_reference",
            "inventory_reservations",
            ["reference_type", "reference_id"],
        )
        op.create_index("idx_inventory_reservations_status", "inventory_reservations", ["status"])


def downgrade() -> None:
    # Drop inventory_reservations table
    if _has_table("inventory_reservations"):
        op.drop_table("inventory_reservations")
