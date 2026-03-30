"""Add platform policy, category mapping, exchange rate, and region rules.

Revision ID: 014
Revises: 013
Create Date: 2026-03-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, UUID


# revision identifiers
revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create platform_policies table
    op.create_table(
        "platform_policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("platform", sa.String(50), nullable=False, index=True),
        sa.Column("region", sa.String(10), nullable=True, index=True),
        sa.Column("policy_type", sa.String(50), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, default=1),
        sa.Column("is_active", sa.Boolean, nullable=False, default=True, index=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("policy_data", JSON, nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Create indexes for platform_policies
    op.create_index(
        "uq_platform_policy_scope_version",
        "platform_policies",
        ["platform", "region", "policy_type", "version"],
        unique=True,
    )
    op.create_index(
        "idx_platform_policy_active",
        "platform_policies",
        ["platform", "region", "policy_type", "is_active"],
        unique=False,
    )

    # Create platform_category_mappings table
    op.create_table(
        "platform_category_mappings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("platform", sa.String(50), nullable=False, index=True),
        sa.Column("region", sa.String(10), nullable=True, index=True),
        sa.Column("internal_category", sa.String(100), nullable=False, index=True),
        sa.Column("platform_category_id", sa.String(100), nullable=False),
        sa.Column("platform_category_name", sa.String(255), nullable=True),
        sa.Column("mapping_version", sa.Integer, nullable=False, default=1),
        sa.Column("is_active", sa.Boolean, nullable=False, default=True, index=True),
        sa.Column("extra_attributes", JSON, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Create indexes for platform_category_mappings
    op.create_index(
        "uq_platform_category_mapping",
        "platform_category_mappings",
        ["platform", "region", "internal_category", "mapping_version"],
        unique=True,
    )
    op.create_index(
        "idx_platform_category_mapping_active",
        "platform_category_mappings",
        ["platform", "region", "is_active"],
        unique=False,
    )

    # Create exchange_rates table
    op.create_table(
        "exchange_rates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("base_currency", sa.String(3), nullable=False, index=True),
        sa.Column("quote_currency", sa.String(3), nullable=False, index=True),
        sa.Column("rate", sa.DECIMAL(18, 8), nullable=False),
        sa.Column("rate_date", sa.Date, nullable=False, index=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, default=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Create indexes for exchange_rates
    op.create_index(
        "uq_exchange_rate_pair_date",
        "exchange_rates",
        ["base_currency", "quote_currency", "rate_date"],
        unique=True,
    )

    # Create region_tax_rules table
    op.create_table(
        "region_tax_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("platform", sa.String(50), nullable=True, index=True),
        sa.Column("region", sa.String(10), nullable=False, index=True),
        sa.Column("tax_type", sa.String(50), nullable=False),
        sa.Column("tax_rate", sa.DECIMAL(8, 4), nullable=False),
        sa.Column("applies_to", JSON, nullable=True),
        sa.Column("version", sa.Integer, nullable=False, default=1),
        sa.Column("is_active", sa.Boolean, nullable=False, default=True, index=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Create indexes for region_tax_rules
    op.create_index(
        "uq_region_tax_rule",
        "region_tax_rules",
        ["platform", "region", "tax_type", "version"],
        unique=True,
    )
    op.create_index(
        "idx_region_tax_rule_active",
        "region_tax_rules",
        ["platform", "region", "is_active"],
        unique=False,
    )

    # Create region_risk_rules table
    op.create_table(
        "region_risk_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("platform", sa.String(50), nullable=True, index=True),
        sa.Column("region", sa.String(10), nullable=False, index=True),
        sa.Column("rule_code", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, default="medium"),
        sa.Column("rule_data", JSON, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, default=1),
        sa.Column("is_active", sa.Boolean, nullable=False, default=True, index=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Create indexes for region_risk_rules
    op.create_index(
        "uq_region_risk_rule",
        "region_risk_rules",
        ["platform", "region", "rule_code", "version"],
        unique=True,
    )
    op.create_index(
        "idx_region_risk_rule_active",
        "region_risk_rules",
        ["platform", "region", "is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("region_risk_rules")
    op.drop_table("region_tax_rules")
    op.drop_table("exchange_rates")
    op.drop_table("platform_category_mappings")
    op.drop_table("platform_policies")
