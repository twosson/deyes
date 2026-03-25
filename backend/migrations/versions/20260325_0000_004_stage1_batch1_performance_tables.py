"""Add Stage 1 Batch 1 performance tables and variant_group.

Revision ID: 004_stage1_batch1_perf
Revises: 003_phase1_schema_alignment
Create Date: 2026-03-25 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "004_stage1_batch1_perf"
down_revision: Union[str, None] = "003_phase1_schema_alignment"
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
    if _has_table("content_assets") and not _has_column("content_assets", "variant_group"):
        op.add_column("content_assets", sa.Column("variant_group", sa.String(length=100), nullable=True))

    if _has_table("content_assets") and not _has_index("content_assets", "idx_content_assets_variant_group"):
        op.create_index(
            "idx_content_assets_variant_group",
            "content_assets",
            ["variant_group"],
            unique=False,
        )

    if not _has_table("listing_performance_daily"):
        op.create_table(
            "listing_performance_daily",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("metric_date", sa.Date(), nullable=False),
            sa.Column("impressions", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("clicks", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("orders", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("units_sold", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("revenue", sa.DECIMAL(precision=12, scale=2), nullable=True),
            sa.Column("ad_spend", sa.DECIMAL(precision=12, scale=2), nullable=True),
            sa.Column("returns_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("refund_amount", sa.DECIMAL(precision=12, scale=2), nullable=True),
            sa.Column("raw_payload", postgresql.JSON(astext_type=sa.Text()), nullable=True),
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
            sa.ForeignKeyConstraint(["listing_id"], ["platform_listings.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    if _has_table("listing_performance_daily") and not _has_index(
        "listing_performance_daily", "idx_listing_performance_daily_listing_id"
    ):
        op.create_index(
            "idx_listing_performance_daily_listing_id",
            "listing_performance_daily",
            ["listing_id"],
            unique=False,
        )
    if _has_table("listing_performance_daily") and not _has_index(
        "listing_performance_daily", "idx_listing_performance_daily_metric_date"
    ):
        op.create_index(
            "idx_listing_performance_daily_metric_date",
            "listing_performance_daily",
            ["metric_date"],
            unique=False,
        )
    if _has_table("listing_performance_daily") and not _has_index(
        "listing_performance_daily", "uq_listing_performance_daily_listing_date"
    ):
        op.create_index(
            "uq_listing_performance_daily_listing_date",
            "listing_performance_daily",
            ["listing_id", "metric_date"],
            unique=True,
        )

    if not _has_table("asset_performance_daily"):
        op.create_table(
            "asset_performance_daily",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("metric_date", sa.Date(), nullable=False),
            sa.Column("impressions", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("clicks", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("orders", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("units_sold", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("revenue", sa.DECIMAL(precision=12, scale=2), nullable=True),
            sa.Column("usage_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("raw_payload", postgresql.JSON(astext_type=sa.Text()), nullable=True),
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
            sa.ForeignKeyConstraint(["asset_id"], ["content_assets.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["listing_id"], ["platform_listings.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    if _has_table("asset_performance_daily") and not _has_index(
        "asset_performance_daily", "idx_asset_performance_daily_asset_id"
    ):
        op.create_index(
            "idx_asset_performance_daily_asset_id",
            "asset_performance_daily",
            ["asset_id"],
            unique=False,
        )
    if _has_table("asset_performance_daily") and not _has_index(
        "asset_performance_daily", "idx_asset_performance_daily_listing_id"
    ):
        op.create_index(
            "idx_asset_performance_daily_listing_id",
            "asset_performance_daily",
            ["listing_id"],
            unique=False,
        )
    if _has_table("asset_performance_daily") and not _has_index(
        "asset_performance_daily", "idx_asset_performance_daily_metric_date"
    ):
        op.create_index(
            "idx_asset_performance_daily_metric_date",
            "asset_performance_daily",
            ["metric_date"],
            unique=False,
        )
    if _has_table("asset_performance_daily") and not _has_index(
        "asset_performance_daily", "uq_asset_performance_daily_asset_listing_date"
    ):
        op.create_index(
            "uq_asset_performance_daily_asset_listing_date",
            "asset_performance_daily",
            ["asset_id", "listing_id", "metric_date"],
            unique=True,
        )


def downgrade() -> None:
    _drop_index_if_exists("asset_performance_daily", "uq_asset_performance_daily_asset_listing_date")
    _drop_index_if_exists("asset_performance_daily", "idx_asset_performance_daily_metric_date")
    _drop_index_if_exists("asset_performance_daily", "idx_asset_performance_daily_listing_id")
    _drop_index_if_exists("asset_performance_daily", "idx_asset_performance_daily_asset_id")
    if _has_table("asset_performance_daily"):
        op.drop_table("asset_performance_daily")

    _drop_index_if_exists("listing_performance_daily", "uq_listing_performance_daily_listing_date")
    _drop_index_if_exists("listing_performance_daily", "idx_listing_performance_daily_metric_date")
    _drop_index_if_exists("listing_performance_daily", "idx_listing_performance_daily_listing_id")
    if _has_table("listing_performance_daily"):
        op.drop_table("listing_performance_daily")

    _drop_index_if_exists("content_assets", "idx_content_assets_variant_group")
    _drop_column_if_exists("content_assets", "variant_group")
