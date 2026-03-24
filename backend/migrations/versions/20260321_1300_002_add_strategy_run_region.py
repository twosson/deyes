"""Add region field to strategy_runs.

Revision ID: 002_add_strategy_run_region
Revises: 001_initial
Create Date: 2026-03-21 13:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_add_strategy_run_region"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("strategy_runs", sa.Column("region", sa.String(length=10), nullable=True))


def downgrade() -> None:
    op.drop_column("strategy_runs", "region")
