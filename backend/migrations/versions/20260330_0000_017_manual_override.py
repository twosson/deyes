"""Add manual override and anomaly detection schema.

Revision ID: 017
Revises: 016
Create Date: 2026-03-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers
revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create manual_overrides table
    op.create_table(
        "manual_overrides",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("override_type", sa.String(50), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("target_id", UUID(as_uuid=True), nullable=False),
        sa.Column("override_data", JSONB, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("cancelled_by", sa.String(100), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_manual_override_target", "manual_overrides", ["target_type", "target_id"])
    op.create_index("idx_manual_override_active", "manual_overrides", ["is_active", "override_type"])
    op.create_index("idx_manual_override_type", "manual_overrides", ["override_type"])

    # Create anomaly_detection_signals table
    op.create_table(
        "anomaly_detection_signals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("target_id", UUID(as_uuid=True), nullable=False),
        sa.Column("anomaly_type", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("anomaly_data", JSONB, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_resolved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(100), nullable=True),
        sa.Column("resolution_notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_anomaly_target", "anomaly_detection_signals", ["target_type", "target_id"])
    op.create_index("idx_anomaly_severity", "anomaly_detection_signals", ["severity", "detected_at"])
    op.create_index("idx_anomaly_resolved", "anomaly_detection_signals", ["is_resolved"])
    op.create_index("idx_anomaly_type", "anomaly_detection_signals", ["anomaly_type"])


def downgrade() -> None:
    op.drop_index("idx_anomaly_type", table_name="anomaly_detection_signals")
    op.drop_index("idx_anomaly_resolved", table_name="anomaly_detection_signals")
    op.drop_index("idx_anomaly_severity", table_name="anomaly_detection_signals")
    op.drop_index("idx_anomaly_target", table_name="anomaly_detection_signals")
    op.drop_table("anomaly_detection_signals")

    op.drop_index("idx_manual_override_type", table_name="manual_overrides")
    op.drop_index("idx_manual_override_active", table_name="manual_overrides")
    op.drop_index("idx_manual_override_target", table_name="manual_overrides")
    op.drop_table("manual_overrides")
