"""Migration: Add LocalizationContent for Phase2.

Revision ID: 010_localization_content
Revises: 009_content_asset_extensions
Create Date: 2026-03-29 00:03:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "010_localization_content"
down_revision: Union[str, None] = "009_content_asset_extensions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table_name)


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    # Create localization_contents table
    if not _has_table("localization_contents"):
        op.create_table(
            "localization_contents",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("language", sa.String(length=10), nullable=False),
            sa.Column("content_type", sa.String(length=50), nullable=False),
            sa.Column("content", postgresql.JSON(astext_type=sa.Text()), nullable=False),
            sa.Column("platform_tags", postgresql.ARRAY(sa.String(length=50)), nullable=True),
            sa.Column("region_tags", postgresql.ARRAY(sa.String(length=10)), nullable=True),
            sa.Column("quality_score", sa.NUMERIC(precision=3, scale=2), nullable=True),
            sa.Column("generated_by", sa.String(length=50), nullable=True),
            sa.Column("reviewed", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["variant_id"], ["product_variants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

        # Create indexes
        op.create_index(
            "idx_localization_contents_variant_id",
            "localization_contents",
            ["variant_id"],
        )
        op.create_index(
            "idx_localization_variant_language",
            "localization_contents",
            ["variant_id", "language", "content_type"],
        )
        op.create_index(
            "uq_localization_variant_language_type",
            "localization_contents",
            ["variant_id", "language", "content_type"],
            unique=True,
        )


def downgrade() -> None:
    if _has_table("localization_contents"):
        op.drop_table("localization_contents")
