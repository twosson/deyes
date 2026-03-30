"""Add action engine schema (ActionRule, ActionExecutionLog).

Revision ID: 016
Revises: 015
Create Date: 2026-03-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers
revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create action_rules table
    op.create_table(
        "action_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("rule_name", sa.String(200), nullable=False),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("trigger_conditions", JSONB, nullable=False),
        sa.Column("target_scope", JSONB, nullable=True),
        sa.Column("action_params", JSONB, nullable=False),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("requires_approval", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_action_rule_name", "action_rules", ["rule_name"], unique=True)
    op.create_index("idx_action_rule_type", "action_rules", ["action_type"])
    op.create_index("idx_action_rule_active", "action_rules", ["is_active", "action_type"])

    # Create action_execution_logs table
    op.create_table(
        "action_execution_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("action_rule_id", UUID(as_uuid=True), sa.ForeignKey("action_rules.id"), nullable=True),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("target_id", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_params", JSONB, nullable=True),
        sa.Column("output_data", JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("approved_by", sa.String(100), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_action_execution_rule", "action_execution_logs", ["action_rule_id"])
    op.create_index("idx_action_execution_status", "action_execution_logs", ["status", "action_type"])
    op.create_index("idx_action_execution_target", "action_execution_logs", ["target_type", "target_id"])
    op.create_index("idx_action_execution_type", "action_execution_logs", ["action_type"])


def downgrade() -> None:
    op.drop_index("idx_action_execution_type", table_name="action_execution_logs")
    op.drop_index("idx_action_execution_target", table_name="action_execution_logs")
    op.drop_index("idx_action_execution_status", table_name="action_execution_logs")
    op.drop_index("idx_action_execution_rule", table_name="action_execution_logs")
    op.drop_table("action_execution_logs")

    op.drop_index("idx_action_rule_active", table_name="action_rules")
    op.drop_index("idx_action_rule_type", table_name="action_rules")
    op.drop_index("idx_action_rule_name", table_name="action_rules")
    op.drop_table("action_rules")
