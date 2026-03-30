"""Add lifecycle engine schema (SkuLifecycleState, LifecycleRule, LifecycleTransitionLog).

Revision ID: 015
Revises: 014
Create Date: 2026-03-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers
revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create sku_lifecycle_states table
    op.create_table(
        "sku_lifecycle_states",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("product_variant_id", UUID(as_uuid=True), sa.ForeignKey("product_variants.id"), nullable=False),
        sa.Column("current_state", sa.String(50), nullable=False),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state_metadata", JSONB, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("uq_sku_lifecycle_state", "sku_lifecycle_states", ["product_variant_id"], unique=True)
    op.create_index("idx_sku_lifecycle_state_current", "sku_lifecycle_states", ["current_state"])
    op.create_index("idx_sku_lifecycle_state_variant", "sku_lifecycle_states", ["product_variant_id"])

    # Create lifecycle_rules table
    op.create_table(
        "lifecycle_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("from_state", sa.String(50), nullable=False),
        sa.Column("to_state", sa.String(50), nullable=False),
        sa.Column("rule_name", sa.String(100), nullable=False),
        sa.Column("conditions", JSONB, nullable=False),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("uq_lifecycle_rule", "lifecycle_rules", ["from_state", "to_state", "rule_name"], unique=True)
    op.create_index("idx_lifecycle_rule_from_state", "lifecycle_rules", ["from_state"])
    op.create_index("idx_lifecycle_rule_to_state", "lifecycle_rules", ["to_state"])
    op.create_index("idx_lifecycle_rule_active", "lifecycle_rules", ["is_active"])

    # Create lifecycle_transition_logs table
    op.create_table(
        "lifecycle_transition_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("product_variant_id", UUID(as_uuid=True), sa.ForeignKey("product_variants.id"), nullable=False),
        sa.Column("from_state", sa.String(50), nullable=False),
        sa.Column("to_state", sa.String(50), nullable=False),
        sa.Column("transitioned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("triggered_by", sa.String(100), nullable=False),
        sa.Column("rule_id", UUID(as_uuid=True), sa.ForeignKey("lifecycle_rules.id"), nullable=True),
        sa.Column("trigger_data", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_lifecycle_transition_variant", "lifecycle_transition_logs", ["product_variant_id"])
    op.create_index("idx_lifecycle_transition_date", "lifecycle_transition_logs", ["transitioned_at"])


def downgrade() -> None:
    op.drop_index("idx_lifecycle_transition_date", table_name="lifecycle_transition_logs")
    op.drop_index("idx_lifecycle_transition_variant", table_name="lifecycle_transition_logs")
    op.drop_table("lifecycle_transition_logs")

    op.drop_index("idx_lifecycle_rule_active", table_name="lifecycle_rules")
    op.drop_index("idx_lifecycle_rule_to_state", table_name="lifecycle_rules")
    op.drop_index("idx_lifecycle_rule_from_state", table_name="lifecycle_rules")
    op.drop_index("uq_lifecycle_rule", table_name="lifecycle_rules")
    op.drop_table("lifecycle_rules")

    op.drop_index("idx_sku_lifecycle_state_variant", table_name="sku_lifecycle_states")
    op.drop_index("idx_sku_lifecycle_state_current", table_name="sku_lifecycle_states")
    op.drop_index("uq_sku_lifecycle_state", table_name="sku_lifecycle_states")
    op.drop_table("sku_lifecycle_states")
