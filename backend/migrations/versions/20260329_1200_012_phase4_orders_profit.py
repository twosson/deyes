"""Migration: Add Phase 4 order/fulfillment/inventory integration schema.

Revision ID: 012_phase4_orders_profit
Revises: 011_platform_content_rule
Create Date: 2026-03-29 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "012_phase4_orders_profit"
down_revision: Union[str, None] = "011_platform_content_rule"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    # Create platform_orders table
    if not _has_table("platform_orders"):
        op.create_table(
            "platform_orders",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("platform", sa.String(length=50), nullable=False),
            sa.Column("region", sa.String(length=10), nullable=False),
            sa.Column("platform_order_id", sa.String(length=100), nullable=False),
            sa.Column("idempotency_key", sa.String(length=255), nullable=False),
            sa.Column("order_status", sa.String(length=50), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False),
            sa.Column("buyer_country", sa.String(length=10), nullable=True),
            sa.Column("total_amount", sa.DECIMAL(precision=12, scale=2), nullable=False),
            sa.Column("ordered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("idempotency_key"),
        )
        op.create_index("idx_platform_orders_platform", "platform_orders", ["platform"])
        op.create_index("idx_platform_orders_region", "platform_orders", ["region"])
        op.create_index("idx_platform_orders_platform_order_id", "platform_orders", ["platform_order_id"])
        op.create_index("idx_platform_orders_idempotency_key", "platform_orders", ["idempotency_key"])
        op.create_index(
            "uq_platform_order",
            "platform_orders",
            ["platform", "platform_order_id"],
            unique=True,
        )

    # Create platform_order_lines table
    if not _has_table("platform_order_lines"):
        op.create_table(
            "platform_order_lines",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("platform_listing_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("product_variant_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("platform_sku", sa.String(length=100), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("unit_price", sa.DECIMAL(precision=10, scale=2), nullable=False),
            sa.Column("gross_revenue", sa.DECIMAL(precision=12, scale=2), nullable=False),
            sa.Column("discount_amount", sa.DECIMAL(precision=12, scale=2), nullable=False),
            sa.Column("line_status", sa.String(length=50), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["order_id"], ["platform_orders.id"]),
            sa.ForeignKeyConstraint(["platform_listing_id"], ["platform_listings.id"]),
            sa.ForeignKeyConstraint(["product_variant_id"], ["product_variants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_platform_order_lines_order_id", "platform_order_lines", ["order_id"])
        op.create_index("idx_platform_order_lines_platform_listing_id", "platform_order_lines", ["platform_listing_id"])
        op.create_index("idx_platform_order_lines_product_variant_id", "platform_order_lines", ["product_variant_id"])
        op.create_index(
            "uq_platform_order_line",
            "platform_order_lines",
            ["order_id", "platform_sku"],
            unique=True,
        )

    # Create fulfillment_records table
    if not _has_table("fulfillment_records"):
        op.create_table(
            "fulfillment_records",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("order_line_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("fulfillment_status", sa.String(length=50), nullable=False),
            sa.Column("carrier", sa.String(length=100), nullable=True),
            sa.Column("tracking_number", sa.String(length=255), nullable=True),
            sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["order_id"], ["platform_orders.id"]),
            sa.ForeignKeyConstraint(["order_line_id"], ["platform_order_lines.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_fulfillment_records_order_id", "fulfillment_records", ["order_id"])
        op.create_index("idx_fulfillment_records_order_line_id", "fulfillment_records", ["order_line_id"])

    # Create refund_cases table
    if not _has_table("refund_cases"):
        op.create_table(
            "refund_cases",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("platform_order_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("platform_order_line_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("product_variant_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("refund_amount", sa.DECIMAL(precision=12, scale=2), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False),
            sa.Column("refund_reason", sa.String(length=50), nullable=False),
            sa.Column("refund_status", sa.String(length=50), nullable=False),
            sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("issue_type", sa.String(length=50), nullable=True),
            sa.Column("attributed_to", sa.String(length=100), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["platform_order_id"], ["platform_orders.id"]),
            sa.ForeignKeyConstraint(["platform_order_line_id"], ["platform_order_lines.id"]),
            sa.ForeignKeyConstraint(["product_variant_id"], ["product_variants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_refund_cases_platform_order_id", "refund_cases", ["platform_order_id"])
        op.create_index("idx_refund_cases_platform_order_line_id", "refund_cases", ["platform_order_line_id"])
        op.create_index("idx_refund_cases_product_variant_id", "refund_cases", ["product_variant_id"])

    # Create settlement_entries table
    if not _has_table("settlement_entries"):
        op.create_table(
            "settlement_entries",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("platform_order_line_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("product_variant_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("entry_type", sa.String(length=50), nullable=False),
            sa.Column("amount", sa.DECIMAL(precision=12, scale=2), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("source_payload", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["platform_order_line_id"], ["platform_order_lines.id"]),
            sa.ForeignKeyConstraint(["product_variant_id"], ["product_variants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_settlement_entries_platform_order_line_id", "settlement_entries", ["platform_order_line_id"])
        op.create_index("idx_settlement_entries_product_variant_id", "settlement_entries", ["product_variant_id"])
        op.create_index(
            "uq_settlement_entry",
            "settlement_entries",
            ["platform_order_line_id", "entry_type"],
            unique=True,
        )

    # Create profit_ledger table
    if not _has_table("profit_ledger"):
        op.create_table(
            "profit_ledger",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("product_variant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("platform_order_line_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("platform_listing_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("gross_revenue", sa.DECIMAL(precision=12, scale=2), nullable=False),
            sa.Column("platform_fee", sa.DECIMAL(precision=12, scale=2), nullable=False),
            sa.Column("refund_loss", sa.DECIMAL(precision=12, scale=2), nullable=False),
            sa.Column("ad_cost", sa.DECIMAL(precision=12, scale=2), nullable=False),
            sa.Column("fulfillment_cost", sa.DECIMAL(precision=12, scale=2), nullable=False),
            sa.Column("net_profit", sa.DECIMAL(precision=12, scale=2), nullable=False),
            sa.Column("profit_margin", sa.DECIMAL(precision=5, scale=2), nullable=True),
            sa.Column("snapshot_date", sa.Date(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["product_variant_id"], ["product_variants.id"]),
            sa.ForeignKeyConstraint(["platform_order_line_id"], ["platform_order_lines.id"]),
            sa.ForeignKeyConstraint(["platform_listing_id"], ["platform_listings.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_profit_ledger_product_variant_id", "profit_ledger", ["product_variant_id"])
        op.create_index("idx_profit_ledger_platform_order_line_id", "profit_ledger", ["platform_order_line_id"])
        op.create_index("idx_profit_ledger_platform_listing_id", "profit_ledger", ["platform_listing_id"])
        op.create_index("idx_profit_ledger_snapshot_date", "profit_ledger", ["snapshot_date"])
        op.create_index(
            "uq_profit_ledger",
            "profit_ledger",
            ["product_variant_id", "platform_order_line_id"],
            unique=True,
        )


def downgrade() -> None:
    # Drop tables in reverse order
    if _has_table("profit_ledger"):
        op.drop_table("profit_ledger")
    if _has_table("settlement_entries"):
        op.drop_table("settlement_entries")
    if _has_table("refund_cases"):
        op.drop_table("refund_cases")
    if _has_table("fulfillment_records"):
        op.drop_table("fulfillment_records")
    if _has_table("platform_order_lines"):
        op.drop_table("platform_order_lines")
    if _has_table("platform_orders"):
        op.drop_table("platform_orders")
