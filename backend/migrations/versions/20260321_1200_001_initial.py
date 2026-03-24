"""Initial migration - create all tables.

Revision ID: 001_initial
Revises:
Create Date: 2026-03-21 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create strategy_runs table
    op.create_table(
        'strategy_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('idempotency_key', sa.String(length=255), nullable=True),
        sa.Column('trigger_type', sa.String(length=20), nullable=False),
        sa.Column('source_platform', sa.String(length=50), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('keywords', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('target_languages', postgresql.ARRAY(sa.String(length=10)), nullable=True),
        sa.Column('price_min', sa.DECIMAL(precision=10, scale=2), nullable=True),
        sa.Column('price_max', sa.DECIMAL(precision=10, scale=2), nullable=True),
        sa.Column('max_candidates', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('requested_by', sa.String(length=100), nullable=True),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_strategy_runs_idempotency_key'), 'strategy_runs', ['idempotency_key'], unique=True)

    # Create agent_runs table
    op.create_table(
        'agent_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('strategy_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('step_name', sa.String(length=100), nullable=False),
        sa.Column('agent_name', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('attempt', sa.Integer(), nullable=False),
        sa.Column('input_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('output_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['strategy_run_id'], ['strategy_runs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_agent_runs_strategy_run_id'), 'agent_runs', ['strategy_run_id'], unique=False)

    # Create candidate_products table
    op.create_table(
        'candidate_products',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('strategy_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_platform', sa.String(length=50), nullable=False),
        sa.Column('source_product_id', sa.String(length=255), nullable=True),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('raw_title', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('currency', sa.String(length=10), nullable=True),
        sa.Column('platform_price', sa.DECIMAL(precision=10, scale=2), nullable=True),
        sa.Column('sales_count', sa.Integer(), nullable=True),
        sa.Column('rating', sa.DECIMAL(precision=3, scale=2), nullable=True),
        sa.Column('main_image_url', sa.Text(), nullable=True),
        sa.Column('raw_payload', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('normalized_attributes', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['strategy_run_id'], ['strategy_runs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_candidate_products_strategy_run_id'), 'candidate_products', ['strategy_run_id'], unique=False)

    # Create supplier_matches table
    op.create_table(
        'supplier_matches',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('candidate_product_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('supplier_name', sa.String(length=255), nullable=True),
        sa.Column('supplier_url', sa.Text(), nullable=True),
        sa.Column('supplier_sku', sa.String(length=255), nullable=True),
        sa.Column('supplier_price', sa.DECIMAL(precision=10, scale=2), nullable=True),
        sa.Column('moq', sa.Integer(), nullable=True),
        sa.Column('confidence_score', sa.DECIMAL(precision=3, scale=2), nullable=True),
        sa.Column('raw_payload', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('selected', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['candidate_product_id'], ['candidate_products.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_supplier_matches_candidate_product_id'), 'supplier_matches', ['candidate_product_id'], unique=False)

    # Create pricing_assessments table
    op.create_table(
        'pricing_assessments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('candidate_product_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('estimated_shipping_cost', sa.DECIMAL(precision=10, scale=2), nullable=True),
        sa.Column('platform_commission_rate', sa.DECIMAL(precision=5, scale=4), nullable=True),
        sa.Column('payment_fee_rate', sa.DECIMAL(precision=5, scale=4), nullable=True),
        sa.Column('return_rate_assumption', sa.DECIMAL(precision=5, scale=4), nullable=True),
        sa.Column('total_cost', sa.DECIMAL(precision=10, scale=2), nullable=True),
        sa.Column('estimated_margin', sa.DECIMAL(precision=10, scale=2), nullable=True),
        sa.Column('margin_percentage', sa.DECIMAL(precision=5, scale=2), nullable=True),
        sa.Column('recommended_price', sa.DECIMAL(precision=10, scale=2), nullable=True),
        sa.Column('profitability_decision', sa.String(length=20), nullable=True),
        sa.Column('explanation', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['candidate_product_id'], ['candidate_products.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_pricing_assessments_candidate_product_id'), 'pricing_assessments', ['candidate_product_id'], unique=True)

    # Create risk_assessments table
    op.create_table(
        'risk_assessments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('candidate_product_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False),
        sa.Column('decision', sa.String(length=20), nullable=False),
        sa.Column('rule_hits', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('llm_notes', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['candidate_product_id'], ['candidate_products.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_risk_assessments_candidate_product_id'), 'risk_assessments', ['candidate_product_id'], unique=True)

    # Create listing_drafts table
    op.create_table(
        'listing_drafts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('candidate_product_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('language', sa.String(length=10), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('bullets', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('seo_keywords', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('prompt_version', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['candidate_product_id'], ['candidate_products.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_listing_drafts_candidate_product_id'), 'listing_drafts', ['candidate_product_id'], unique=False)

    # Create run_events table
    op.create_table(
        'run_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('strategy_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('agent_run_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('event_payload', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['agent_run_id'], ['agent_runs.id'], ),
        sa.ForeignKeyConstraint(['strategy_run_id'], ['strategy_runs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_run_events_agent_run_id'), 'run_events', ['agent_run_id'], unique=False)
    op.create_index(op.f('ix_run_events_strategy_run_id'), 'run_events', ['strategy_run_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_run_events_strategy_run_id'), table_name='run_events')
    op.drop_index(op.f('ix_run_events_agent_run_id'), table_name='run_events')
    op.drop_table('run_events')
    op.drop_index(op.f('ix_listing_drafts_candidate_product_id'), table_name='listing_drafts')
    op.drop_table('listing_drafts')
    op.drop_index(op.f('ix_risk_assessments_candidate_product_id'), table_name='risk_assessments')
    op.drop_table('risk_assessments')
    op.drop_index(op.f('ix_pricing_assessments_candidate_product_id'), table_name='pricing_assessments')
    op.drop_table('pricing_assessments')
    op.drop_index(op.f('ix_supplier_matches_candidate_product_id'), table_name='supplier_matches')
    op.drop_table('supplier_matches')
    op.drop_index(op.f('ix_candidate_products_strategy_run_id'), table_name='candidate_products')
    op.drop_table('candidate_products')
    op.drop_index(op.f('ix_agent_runs_strategy_run_id'), table_name='agent_runs')
    op.drop_table('agent_runs')
    op.drop_index(op.f('ix_strategy_runs_idempotency_key'), table_name='strategy_runs')
    op.drop_table('strategy_runs')
