"""Migration: Add PlatformContentRule for Phase2.

Revision ID: 011_platform_content_rule
Revises: 010_localization_content
Create Date: 2026-03-29 00:04:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "011_platform_content_rule"
down_revision: Union[str, None] = "010_localization_content"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table_name)


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    # Create platform_content_rules table
    if not _has_table("platform_content_rules"):
        op.create_table(
            "platform_content_rules",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("platform", sa.String(length=50), nullable=False),
            sa.Column("asset_type", sa.String(length=50), nullable=False),
            sa.Column("image_spec", postgresql.JSON(astext_type=sa.Text()), nullable=False),
            sa.Column("allow_text_on_image", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("max_images", sa.Integer(), nullable=False),
            sa.Column(
                "required_languages",
                postgresql.ARRAY(sa.String(length=10)),
                nullable=False,
                server_default=sa.text("ARRAY['en']"),
            ),
            sa.Column("compliance_requirements", postgresql.JSON(astext_type=sa.Text()), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

        # Create indexes
        op.create_index("idx_platform_content_rules_platform", "platform_content_rules", ["platform"])
        op.create_index(
            "uq_platform_content_rule",
            "platform_content_rules",
            ["platform", "asset_type"],
            unique=True,
        )

        # Insert default rules for common platforms
        op.execute("""
            INSERT INTO platform_content_rules
            (id, platform, asset_type, image_spec, allow_text_on_image, max_images, required_languages, compliance_requirements)
            VALUES
            (
                gen_random_uuid(),
                'temu',
                'main_image',
                '{"width": 800, "height": 800, "format": "jpg", "max_file_size_mb": 5, "min_dpi": 72}'::jsonb,
                true,
                9,
                ARRAY['en'],
                '{"no_medical_claims": true, "no_before_after": true}'::jsonb
            ),
            (
                gen_random_uuid(),
                'amazon',
                'main_image',
                '{"width": 1000, "height": 1000, "format": "jpg", "max_file_size_mb": 10, "min_dpi": 72}'::jsonb,
                false,
                7,
                ARRAY['en'],
                '{"no_medical_claims": true, "no_before_after": true, "no_competitive": true}'::jsonb
            ),
            (
                gen_random_uuid(),
                'ozon',
                'main_image',
                '{"width": 1200, "height": 1200, "format": "jpg", "max_file_size_mb": 8, "min_dpi": 72}'::jsonb,
                true,
                15,
                ARRAY['ru'],
                '{"no_medical_claims": true}'::jsonb
            ),
            (
                gen_random_uuid(),
                'aliexpress',
                'main_image',
                '{"width": 800, "height": 800, "format": "jpg", "max_file_size_mb": 5, "min_dpi": 72}'::jsonb,
                true,
                10,
                ARRAY['en'],
                '{"no_medical_claims": true}'::jsonb
            ),
            (
                gen_random_uuid(),
                'tiktok_shop',
                'main_image',
                '{"width": 1024, "height": 1024, "format": "jpg", "max_file_size_mb": 5, "min_dpi": 72}'::jsonb,
                true,
                9,
                ARRAY['en'],
                '{"no_medical_claims": true, "no_before_after": true}'::jsonb
            ),
            (
                gen_random_uuid(),
                'mercado_libre',
                'main_image',
                '{"width": 1000, "height": 1000, "format": "jpg", "max_file_size_mb": 8, "min_dpi": 72}'::jsonb,
                true,
                10,
                ARRAY['es'],
                '{"no_medical_claims": true}'::jsonb
            )
        """)


def downgrade() -> None:
    if _has_table("platform_content_rules"):
        op.drop_table("platform_content_rules")
