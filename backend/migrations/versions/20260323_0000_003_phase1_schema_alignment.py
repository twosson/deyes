"""Align Phase 1 schema with ORM and API usage.

Revision ID: 003_phase1_schema_alignment
Revises: 002_add_strategy_run_region
Create Date: 2026-03-23 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "003_phase1_schema_alignment"
down_revision: Union[str, None] = "002_add_strategy_run_region"
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


def _drop_index_if_exists(table_name: str, index_name: str) -> None:
    if _has_table(table_name) and _has_index(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    if _has_table(table_name) and _has_column(table_name, column_name):
        op.drop_column(table_name, column_name)


def upgrade() -> None:
    # Align candidate_products with the current ORM/API contract.
    if not _has_column("candidate_products", "internal_sku"):
        op.add_column("candidate_products", sa.Column("internal_sku", sa.String(length=50), nullable=True))

    if not _has_column("candidate_products", "lifecycle_status"):
        op.add_column(
            "candidate_products",
            sa.Column(
                "lifecycle_status",
                sa.String(length=50),
                nullable=True,
                server_default=sa.text("'DRAFT'"),
            ),
        )

    if not _has_column("candidate_products", "updated_at"):
        op.add_column(
            "candidate_products",
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )

    if not _has_index("candidate_products", "idx_candidate_products_internal_sku"):
        op.create_index(
            "idx_candidate_products_internal_sku",
            "candidate_products",
            ["internal_sku"],
            unique=True,
        )

    if not _has_index("candidate_products", "idx_candidate_products_lifecycle_status"):
        op.create_index(
            "idx_candidate_products_lifecycle_status",
            "candidate_products",
            ["lifecycle_status"],
            unique=False,
        )

    # Phase 1 tables.
    if not _has_table("content_assets"):
        op.create_table(
            "content_assets",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("candidate_product_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("asset_type", sa.String(length=50), nullable=False),
            sa.Column("style_tags", postgresql.ARRAY(sa.String(length=50)), nullable=True),
            sa.Column("platform_tags", postgresql.ARRAY(sa.String(length=50)), nullable=True),
            sa.Column("region_tags", postgresql.ARRAY(sa.String(length=10)), nullable=True),
            sa.Column("file_url", sa.Text(), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=True),
            sa.Column("dimensions", sa.String(length=20), nullable=True),
            sa.Column("format", sa.String(length=10), nullable=True),
            sa.Column("ai_quality_score", sa.DECIMAL(precision=3, scale=1), nullable=True),
            sa.Column("human_approved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("approval_notes", sa.Text(), nullable=True),
            sa.Column("usage_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("conversion_rate", sa.DECIMAL(precision=5, scale=4), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("parent_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("generation_params", postgresql.JSON(astext_type=sa.Text()), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(
                ["candidate_product_id"],
                ["candidate_products.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["parent_asset_id"],
                ["content_assets.id"],
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_index("content_assets", "idx_content_assets_candidate_product_id"):
        op.create_index(
            "idx_content_assets_candidate_product_id",
            "content_assets",
            ["candidate_product_id"],
            unique=False,
        )
    if not _has_index("content_assets", "idx_content_assets_asset_type"):
        op.create_index("idx_content_assets_asset_type", "content_assets", ["asset_type"], unique=False)
    if not _has_index("content_assets", "idx_content_assets_parent_asset_id"):
        op.create_index(
            "idx_content_assets_parent_asset_id",
            "content_assets",
            ["parent_asset_id"],
            unique=False,
        )

    if not _has_table("platform_listings"):
        op.create_table(
            "platform_listings",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("candidate_product_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("platform", sa.String(length=50), nullable=False),
            sa.Column("region", sa.String(length=10), nullable=False),
            sa.Column("platform_listing_id", sa.String(length=100), nullable=True),
            sa.Column("platform_url", sa.Text(), nullable=True),
            sa.Column("price", sa.DECIMAL(precision=10, scale=2), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False),
            sa.Column("inventory", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column(
                "status",
                sa.String(length=50),
                nullable=False,
                server_default=sa.text("'pending'"),
            ),
            sa.Column("platform_data", postgresql.JSON(astext_type=sa.Text()), nullable=True),
            sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("sync_error", sa.Text(), nullable=True),
            sa.Column("total_sales", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("total_revenue", sa.DECIMAL(precision=12, scale=2), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.ForeignKeyConstraint(
                ["candidate_product_id"],
                ["candidate_products.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_index("platform_listings", "idx_platform_listings_candidate_product_id"):
        op.create_index(
            "idx_platform_listings_candidate_product_id",
            "platform_listings",
            ["candidate_product_id"],
            unique=False,
        )
    if not _has_index("platform_listings", "idx_platform_listings_platform"):
        op.create_index("idx_platform_listings_platform", "platform_listings", ["platform"], unique=False)
    if not _has_index("platform_listings", "idx_platform_listings_region"):
        op.create_index("idx_platform_listings_region", "platform_listings", ["region"], unique=False)
    if not _has_index("platform_listings", "idx_platform_listings_platform_listing_id"):
        op.create_index(
            "idx_platform_listings_platform_listing_id",
            "platform_listings",
            ["platform_listing_id"],
            unique=False,
        )
    if not _has_index("platform_listings", "idx_platform_listings_status"):
        op.create_index("idx_platform_listings_status", "platform_listings", ["status"], unique=False)

    if not _has_table("listing_asset_associations"):
        op.create_table(
            "listing_asset_associations",
            sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("display_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("is_main", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.ForeignKeyConstraint(["asset_id"], ["content_assets.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["listing_id"], ["platform_listings.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("listing_id", "asset_id"),
        )

    if not _has_index("listing_asset_associations", "idx_listing_asset_associations_listing_id"):
        op.create_index(
            "idx_listing_asset_associations_listing_id",
            "listing_asset_associations",
            ["listing_id"],
            unique=False,
        )
    if not _has_index("listing_asset_associations", "idx_listing_asset_associations_asset_id"):
        op.create_index(
            "idx_listing_asset_associations_asset_id",
            "listing_asset_associations",
            ["asset_id"],
            unique=False,
        )

    if not _has_table("inventory_sync_logs"):
        op.create_table(
            "inventory_sync_logs",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("old_inventory", sa.Integer(), nullable=False),
            sa.Column("new_inventory", sa.Integer(), nullable=False),
            sa.Column("sync_status", sa.String(length=20), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["listing_id"], ["platform_listings.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_index("inventory_sync_logs", "idx_inventory_sync_logs_listing_id"):
        op.create_index(
            "idx_inventory_sync_logs_listing_id",
            "inventory_sync_logs",
            ["listing_id"],
            unique=False,
        )
    if not _has_index("inventory_sync_logs", "idx_inventory_sync_logs_synced_at"):
        op.create_index(
            "idx_inventory_sync_logs_synced_at",
            "inventory_sync_logs",
            ["synced_at"],
            unique=False,
        )

    if not _has_table("price_history"):
        op.create_table(
            "price_history",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("old_price", sa.DECIMAL(precision=10, scale=2), nullable=False),
            sa.Column("new_price", sa.DECIMAL(precision=10, scale=2), nullable=False),
            sa.Column("reason", sa.String(length=200), nullable=True),
            sa.Column("changed_by", sa.String(length=100), nullable=True),
            sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["listing_id"], ["platform_listings.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _has_index("price_history", "idx_price_history_listing_id"):
        op.create_index("idx_price_history_listing_id", "price_history", ["listing_id"], unique=False)
    if not _has_index("price_history", "idx_price_history_changed_at"):
        op.create_index("idx_price_history_changed_at", "price_history", ["changed_at"], unique=False)


def downgrade() -> None:
    _drop_index_if_exists("price_history", "idx_price_history_changed_at")
    _drop_index_if_exists("price_history", "idx_price_history_listing_id")
    if _has_table("price_history"):
        op.drop_table("price_history")

    _drop_index_if_exists("inventory_sync_logs", "idx_inventory_sync_logs_synced_at")
    _drop_index_if_exists("inventory_sync_logs", "idx_inventory_sync_logs_listing_id")
    if _has_table("inventory_sync_logs"):
        op.drop_table("inventory_sync_logs")

    _drop_index_if_exists("listing_asset_associations", "idx_listing_asset_associations_asset_id")
    _drop_index_if_exists("listing_asset_associations", "idx_listing_asset_associations_listing_id")
    if _has_table("listing_asset_associations"):
        op.drop_table("listing_asset_associations")

    _drop_index_if_exists("platform_listings", "idx_platform_listings_status")
    _drop_index_if_exists("platform_listings", "idx_platform_listings_platform_listing_id")
    _drop_index_if_exists("platform_listings", "idx_platform_listings_region")
    _drop_index_if_exists("platform_listings", "idx_platform_listings_platform")
    _drop_index_if_exists("platform_listings", "idx_platform_listings_candidate_product_id")
    if _has_table("platform_listings"):
        op.drop_table("platform_listings")

    _drop_index_if_exists("content_assets", "idx_content_assets_parent_asset_id")
    _drop_index_if_exists("content_assets", "idx_content_assets_asset_type")
    _drop_index_if_exists("content_assets", "idx_content_assets_candidate_product_id")
    if _has_table("content_assets"):
        op.drop_table("content_assets")

    _drop_index_if_exists("candidate_products", "idx_candidate_products_lifecycle_status")
    _drop_index_if_exists("candidate_products", "idx_candidate_products_internal_sku")
    _drop_column_if_exists("candidate_products", "updated_at")
    _drop_column_if_exists("candidate_products", "lifecycle_status")
    _drop_column_if_exists("candidate_products", "internal_sku")
