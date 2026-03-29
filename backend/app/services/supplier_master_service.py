"""Supplier master and offer normalization service.

Normalizes SupplierMatch evidence records into long-lived Supplier and SupplierOffer
entities for the ERP Lite core fact layer.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import SupplierStatus
from app.core.logging import get_logger
from app.db.models import ProductMaster, ProductVariant, Supplier, SupplierMatch, SupplierOffer

logger = get_logger(__name__)


@dataclass
class SupplierResolutionResult:
    """Result of resolving supplier master and offer."""

    supplier: Supplier
    offer: SupplierOffer
    is_new_supplier: bool
    is_new_offer: bool


class SupplierMasterService:
    """Service for normalizing supplier evidence into master entities."""

    def __init__(self):
        self.logger = get_logger(__name__)

    def _normalize_supplier_name(self, name: Optional[str]) -> Optional[str]:
        """Normalize supplier name for matching."""
        if not name:
            return None
        return name.strip().lower()

    async def _find_supplier_by_url(
        self,
        supplier_url: Optional[str],
        db: AsyncSession,
    ) -> Optional[Supplier]:
        """Find supplier by exact URL in metadata in a DB-portable way."""
        if not supplier_url:
            return None

        stmt = select(Supplier).where(Supplier.metadata_.is_not(None))
        result = await db.execute(stmt)
        for supplier in result.scalars().all():
            metadata = supplier.metadata_ or {}
            if metadata.get("supplier_url") == supplier_url:
                return supplier
        return None

    async def resolve_supplier_entity(
        self,
        supplier_match_id: UUID,
        variant_id: UUID,
        db: AsyncSession,
    ) -> SupplierResolutionResult:
        """Resolve or create Supplier and SupplierOffer from SupplierMatch.

        Matching priority:
        1. Exact supplier_url
        2. Normalized supplier_name
        """
        supplier_match = await db.get(SupplierMatch, supplier_match_id)
        if not supplier_match:
            raise ValueError(f"SupplierMatch {supplier_match_id} not found")

        variant = await db.get(ProductVariant, variant_id)
        if not variant:
            raise ValueError(f"ProductVariant {variant_id} not found")

        existing_supplier = await self._find_supplier_by_url(
            supplier_match.supplier_url,
            db,
        )

        if not existing_supplier and supplier_match.supplier_name:
            normalized_name = self._normalize_supplier_name(supplier_match.supplier_name)
            name_stmt = select(Supplier).where(Supplier.name.ilike(f"%{normalized_name}%"))
            name_result = await db.execute(name_stmt)
            existing_supplier = name_result.scalar_one_or_none()

        is_new_supplier = False
        if not existing_supplier:
            supplier = Supplier(
                id=uuid4(),
                name=supplier_match.supplier_name or "Unknown Supplier",
                alibaba_id=supplier_match.raw_payload.get("alibaba_id") if supplier_match.raw_payload else None,
                contact_email=None,
                contact_phone=None,
                status=SupplierStatus.ACTIVE,
                metadata_={
                    "source": "supplier_match_normalization",
                    "supplier_url": supplier_match.supplier_url,
                    "raw_payload": supplier_match.raw_payload,
                },
            )
            db.add(supplier)
            await db.flush()
            is_new_supplier = True
        else:
            supplier = existing_supplier

        offer_stmt = select(SupplierOffer).where(
            SupplierOffer.supplier_id == supplier.id,
            SupplierOffer.variant_id == variant_id,
        )
        offer_result = await db.execute(offer_stmt)
        existing_offer = offer_result.scalar_one_or_none()

        is_new_offer = False
        if not existing_offer:
            offer = SupplierOffer(
                id=uuid4(),
                supplier_id=supplier.id,
                variant_id=variant_id,
                unit_price=supplier_match.supplier_price or Decimal("0.00"),
                currency="USD",
                moq=supplier_match.moq or 1,
                lead_time_days=30,
            )
            db.add(offer)
            await db.flush()
            is_new_offer = True
        else:
            existing_offer.unit_price = supplier_match.supplier_price or existing_offer.unit_price
            existing_offer.moq = supplier_match.moq or existing_offer.moq
            offer = existing_offer

        await db.commit()
        await db.refresh(supplier)
        await db.refresh(offer)

        self.logger.info(
            "supplier_resolved",
            supplier_match_id=str(supplier_match_id),
            supplier_id=str(supplier.id),
            variant_id=str(variant_id),
            is_new_supplier=is_new_supplier,
            is_new_offer=is_new_offer,
        )

        return SupplierResolutionResult(
            supplier=supplier,
            offer=offer,
            is_new_supplier=is_new_supplier,
            is_new_offer=is_new_offer,
        )

    async def resolve_primary_supplier_for_variant(
        self,
        variant_id: UUID,
        db: AsyncSession,
    ) -> Optional[SupplierResolutionResult]:
        """Resolve the primary supplier for a variant from the selected SupplierMatch."""
        variant = await db.get(ProductVariant, variant_id)
        if not variant:
            return None

        master_stmt = select(ProductMaster).where(ProductMaster.id == variant.master_id)
        master_result = await db.execute(master_stmt)
        master = master_result.scalar_one_or_none()
        if not master or not master.candidate_product_id:
            return None

        selected_stmt = select(SupplierMatch).where(
            SupplierMatch.candidate_product_id == master.candidate_product_id,
            SupplierMatch.selected.is_(True),
        )
        selected_result = await db.execute(selected_stmt)
        selected_match = selected_result.scalar_one_or_none()

        if not selected_match:
            return None

        return await self.resolve_supplier_entity(selected_match.id, variant_id, db)
