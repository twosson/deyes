"""Add Experiment table for A/B testing.

Revision ID: 005_stage1_batch3_exp
Revises: 004_stage1_batch1_perf
Create Date: 2026-03-25 01:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "005_stage1_batch3_exp"
down_revision: Union[str, None] = "004_stage1_batch1_perf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table_name)


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _drop_index_if_exists(table_name: str, index_name: str) -> None:
    if _has_table(table_name) and _has_index(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    if not _has_table("experiments"):
        op.create_table(
            "experiments",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("candidate_product_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column(
                "status",
                sa.String(length=50),
                nullable=False,
                server_default=sa.text("'draft'"),
            ),
            sa.Column("target_platform", sa.String(length=50), nullable=True),
            sa.Column("region", sa.String(length=10), nullable=True),
            sa.Column(
                "metric_goal",
                sa.String(length=50),
                nullable=False,
                server_default=sa.text("'ctr'"),
            ),
            sa.Column("winner_variant_group", sa.String(length=100), nullable=True),
            sa.Column("winner_selected_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("metadata", postgresql.JSON(astext_type=sa.Text()), nullable=True),
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
            sa.ForeignKeyConstraint(["candidate_product_id"], ["candidate_products.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    if _has_table("experiments") and not _has_index("experiments", "idx_experiments_candidate_product_id"):
        op.create_index(
            "idx_experiments_candidate_product_id",
            "experiments",
            ["candidate_product_id"],
            unique=False,
        )

    if _has_table("experiments") and not _has_index("experiments", "idx_experiments_status"):
        op.create_index(
            "idx_experiments_status",
            "experiments",
            ["status"],
            unique=False,
        )


def downgrade() -> None:
    _drop_index_if_exists("experiments", "idx_experiments_status")
    _drop_index_if_exists("experiments", "idx_experiments_candidate_product_id")
    if _has_table("experiments"):
        op.drop_table("experiments")
