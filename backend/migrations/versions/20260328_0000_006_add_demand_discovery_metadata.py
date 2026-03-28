"""Add demand_discovery_metadata to candidate_products.

Revision ID: 006_demand_discovery_metadata
Revises: 005_stage1_batch3_exp
Create Date: 2026-03-28 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "006_demand_discovery_metadata"
down_revision: Union[str, None] = "005_stage1_batch3_exp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if _has_table("candidate_products") and not _has_column("candidate_products", "demand_discovery_metadata"):
        op.add_column(
            "candidate_products",
            sa.Column("demand_discovery_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )


def downgrade() -> None:
    if _has_table("candidate_products") and _has_column("candidate_products", "demand_discovery_metadata"):
        op.drop_column("candidate_products", "demand_discovery_metadata")
