"""Migration: Extend ContentAsset for Phase2 localization.

Revision ID: 009_content_asset_extensions
Revises: 008_inventory_reservation
Create Date: 2026-03-29 00:02:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "009_content_asset_extensions"
down_revision: Union[str, None] = "008_inventory_reservation"
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
    # Extend content_assets table
    if _has_table("content_assets"):
        # Add language_tags column
        if not _has_column("content_assets", "language_tags"):
            op.add_column(
                "content_assets",
                sa.Column("language_tags", postgresql.ARRAY(sa.String(length=10)), nullable=True),
            )

        # Add spec column
        if not _has_column("content_assets", "spec"):
            op.add_column(
                "content_assets",
                sa.Column("spec", postgresql.JSON(astext_type=sa.Text()), nullable=True),
            )

        # Add compliance_tags column
        if not _has_column("content_assets", "compliance_tags"):
            op.add_column(
                "content_assets",
                sa.Column("compliance_tags", postgresql.ARRAY(sa.String(length=50)), nullable=True),
            )

        # Add usage_scope column
        if not _has_column("content_assets", "usage_scope"):
            op.add_column(
                "content_assets",
                sa.Column("usage_scope", sa.String(length=50), nullable=True),
            )

        # Create index on usage_scope
        if not _has_index("content_assets", "idx_content_assets_usage_scope"):
            op.create_index(
                "idx_content_assets_usage_scope",
                "content_assets",
                ["usage_scope"],
            )

        # Create index on parent_asset_id if not exists
        if not _has_index("content_assets", "idx_content_assets_parent_asset_id"):
            op.create_index(
                "idx_content_assets_parent_asset_id",
                "content_assets",
                ["parent_asset_id"],
            )


def downgrade() -> None:
    # Remove Phase2 extensions from content_assets
    if _has_table("content_assets"):
        if _has_index("content_assets", "idx_content_assets_parent_asset_id"):
            op.drop_index("idx_content_assets_parent_asset_id", "content_assets")

        if _has_index("content_assets", "idx_content_assets_usage_scope"):
            op.drop_index("idx_content_assets_usage_scope", "content_assets")

        if _has_column("content_assets", "usage_scope"):
            op.drop_column("content_assets", "usage_scope")

        if _has_column("content_assets", "compliance_tags"):
            op.drop_column("content_assets", "compliance_tags")

        if _has_column("content_assets", "spec"):
            op.drop_column("content_assets", "spec")

        if _has_column("content_assets", "language_tags"):
            op.drop_column("content_assets", "language_tags")
