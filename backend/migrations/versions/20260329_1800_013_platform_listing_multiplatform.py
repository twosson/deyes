"""Add marketplace field and multi-platform indexes to platform_listings.

Revision ID: 013
Revises: 012
Create Date: 2026-03-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers
revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add marketplace column (nullable, default NULL for existing records)
    op.add_column(
        "platform_listings",
        sa.Column("marketplace", sa.String(50), nullable=True, index=True),
    )

    # Add composite unique index: platform + marketplace + platform_listing_id
    # Only enforced when platform_listing_id is not null (partial uniqueness)
    op.create_index(
        "idx_platform_marketplace_listing",
        "platform_listings",
        ["platform", "marketplace", "platform_listing_id"],
        unique=False,  # Allow NULL listing_ids (draft records)
    )

    # Add composite query index: product_variant_id + platform + region
    op.create_index(
        "idx_variant_platform_region",
        "platform_listings",
        ["product_variant_id", "platform", "region"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_variant_platform_region", table_name="platform_listings")
    op.drop_index("idx_platform_marketplace_listing", table_name="platform_listings")
    op.drop_column("platform_listings", "marketplace")
