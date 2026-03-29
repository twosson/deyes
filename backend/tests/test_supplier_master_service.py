"""Tests for SupplierMasterService."""
import pytest
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    CandidateStatus,
    InventoryMode,
    ProductMasterStatus,
    ProductVariantStatus,
    SourcePlatform,
    StrategyRunStatus,
    SupplierStatus,
    TriggerType,
)
from app.db.models import (
    CandidateProduct,
    ProductMaster,
    ProductVariant,
    StrategyRun,
    Supplier,
    SupplierMatch,
)
from app.services.supplier_master_service import SupplierMasterService


async def _create_strategy_run(db_session: AsyncSession) -> StrategyRun:
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.QUEUED,
        max_candidates=5,
    )
    db_session.add(strategy_run)
    await db_session.flush()
    return strategy_run


async def _create_candidate(db_session: AsyncSession, strategy_run_id) -> CandidateProduct:
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run_id,
        source_platform=SourcePlatform.ALIBABA_1688,
        title="Supplier Candidate",
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)
    await db_session.flush()
    return candidate


async def _create_variant_for_candidate(db_session: AsyncSession, candidate: CandidateProduct) -> ProductVariant:
    master = ProductMaster(
        id=uuid4(),
        candidate_product_id=candidate.id,
        internal_sku="SKU-SUP-001",
        name="Supplier Product",
        status=ProductMasterStatus.ACTIVE,
    )
    db_session.add(master)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="SKU-SUP-001",
        attributes={},
        inventory_mode=InventoryMode.STOCK_FIRST,
        status=ProductVariantStatus.ACTIVE,
    )
    db_session.add(variant)
    await db_session.flush()
    return variant


@pytest.mark.asyncio
async def test_resolve_supplier_entity_creates_supplier_and_offer(db_session: AsyncSession):
    """resolve_supplier_entity should create Supplier and SupplierOffer."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    variant = await _create_variant_for_candidate(db_session, candidate)

    match = SupplierMatch(
        id=uuid4(),
        candidate_product_id=candidate.id,
        supplier_name="Acme Supplier",
        supplier_url="https://example.com/acme",
        supplier_price=Decimal("12.50"),
        moq=50,
        raw_payload={"alibaba_id": "A123"},
        selected=True,
    )
    db_session.add(match)
    await db_session.commit()

    service = SupplierMasterService()
    result = await service.resolve_supplier_entity(match.id, variant.id, db_session)

    assert result.is_new_supplier is True
    assert result.is_new_offer is True
    assert result.supplier.name == "Acme Supplier"
    assert result.offer.variant_id == variant.id
    assert result.offer.unit_price == Decimal("12.50")
    assert result.offer.moq == 50


@pytest.mark.asyncio
async def test_resolve_supplier_entity_reuses_supplier_by_url(db_session: AsyncSession):
    """resolve_supplier_entity should reuse existing supplier with same URL."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    variant = await _create_variant_for_candidate(db_session, candidate)

    existing_supplier = Supplier(
        id=uuid4(),
        name="Existing Supplier",
        status=SupplierStatus.ACTIVE,
        metadata_={"supplier_url": "https://example.com/acme"},
    )
    db_session.add(existing_supplier)
    await db_session.flush()

    match = SupplierMatch(
        id=uuid4(),
        candidate_product_id=candidate.id,
        supplier_name="Acme Supplier",
        supplier_url="https://example.com/acme",
        supplier_price=Decimal("10.00"),
        moq=20,
        selected=True,
    )
    db_session.add(match)
    await db_session.commit()

    service = SupplierMasterService()
    result = await service.resolve_supplier_entity(match.id, variant.id, db_session)

    assert result.is_new_supplier is False
    assert result.supplier.id == existing_supplier.id
    assert result.offer.supplier_id == existing_supplier.id


@pytest.mark.asyncio
async def test_resolve_supplier_entity_reuses_supplier_by_name(db_session: AsyncSession):
    """resolve_supplier_entity should reuse existing supplier by normalized name."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    variant = await _create_variant_for_candidate(db_session, candidate)

    existing_supplier = Supplier(
        id=uuid4(),
        name="Acme Supplier Co",
        status=SupplierStatus.ACTIVE,
    )
    db_session.add(existing_supplier)
    await db_session.flush()

    match = SupplierMatch(
        id=uuid4(),
        candidate_product_id=candidate.id,
        supplier_name="acme supplier",
        supplier_price=Decimal("11.00"),
        moq=30,
        selected=True,
    )
    db_session.add(match)
    await db_session.commit()

    service = SupplierMasterService()
    result = await service.resolve_supplier_entity(match.id, variant.id, db_session)

    assert result.is_new_supplier is False
    assert result.supplier.id == existing_supplier.id


@pytest.mark.asyncio
async def test_resolve_supplier_entity_updates_existing_offer(db_session: AsyncSession):
    """resolve_supplier_entity should update existing offer pricing and MOQ."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    variant = await _create_variant_for_candidate(db_session, candidate)

    supplier = Supplier(
        id=uuid4(),
        name="Offer Supplier",
        status=SupplierStatus.ACTIVE,
        metadata_={"supplier_url": "https://example.com/offer"},
    )
    db_session.add(supplier)
    await db_session.flush()

    from app.db.models import SupplierOffer
    existing_offer = SupplierOffer(
        id=uuid4(),
        supplier_id=supplier.id,
        variant_id=variant.id,
        unit_price=Decimal("9.99"),
        currency="USD",
        moq=10,
        lead_time_days=30,
    )
    db_session.add(existing_offer)
    await db_session.flush()

    match = SupplierMatch(
        id=uuid4(),
        candidate_product_id=candidate.id,
        supplier_name="Offer Supplier",
        supplier_url="https://example.com/offer",
        supplier_price=Decimal("8.88"),
        moq=100,
        selected=True,
    )
    db_session.add(match)
    await db_session.commit()

    service = SupplierMasterService()
    result = await service.resolve_supplier_entity(match.id, variant.id, db_session)

    assert result.is_new_offer is False
    assert result.offer.id == existing_offer.id
    assert result.offer.unit_price == Decimal("8.88")
    assert result.offer.moq == 100


@pytest.mark.asyncio
async def test_resolve_primary_supplier_for_variant(db_session: AsyncSession):
    """resolve_primary_supplier_for_variant should use selected SupplierMatch."""
    strategy_run = await _create_strategy_run(db_session)
    candidate = await _create_candidate(db_session, strategy_run.id)
    variant = await _create_variant_for_candidate(db_session, candidate)

    match = SupplierMatch(
        id=uuid4(),
        candidate_product_id=candidate.id,
        supplier_name="Primary Supplier",
        supplier_url="https://example.com/primary",
        supplier_price=Decimal("15.00"),
        moq=25,
        selected=True,
    )
    db_session.add(match)
    await db_session.commit()

    service = SupplierMasterService()
    result = await service.resolve_primary_supplier_for_variant(variant.id, db_session)

    assert result is not None
    assert result.supplier.name == "Primary Supplier"
    assert result.offer.variant_id == variant.id
