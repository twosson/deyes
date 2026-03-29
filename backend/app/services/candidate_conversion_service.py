"""Candidate to master/variant conversion service.

Handles conversion of discovered candidates into master products with variants,
enabling multi-platform and multi-region publishing strategies.
"""
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import CandidateProduct, PricingAssessment, ProductMaster, RiskAssessment
from app.services.product_master_service import ProductMasterService

logger = get_logger(__name__)


class CandidateConversionResult:
    """Result of candidate conversion."""

    def __init__(
        self,
        master_candidate_id: UUID,
        variant_candidate_ids: list[UUID],
        conversion_reason: str,
        is_master: bool,
        product_master_id: Optional[UUID] = None,
        product_variant_id: Optional[UUID] = None,
    ):
        self.master_candidate_id = master_candidate_id
        self.variant_candidate_ids = variant_candidate_ids
        self.conversion_reason = conversion_reason
        self.is_master = is_master
        self.product_master_id = product_master_id
        self.product_variant_id = product_variant_id

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "master_candidate_id": str(self.master_candidate_id),
            "variant_candidate_ids": [str(vid) for vid in self.variant_candidate_ids],
            "conversion_reason": self.conversion_reason,
            "is_master": self.is_master,
            "product_master_id": str(self.product_master_id) if self.product_master_id else None,
            "product_variant_id": str(self.product_variant_id) if self.product_variant_id else None,
        }


class CandidateConversionService:
    """Service for converting candidates to master/variant structure."""

    def __init__(self):
        self.product_master_service = ProductMasterService()

    async def convert_candidate_to_master(
        self,
        candidate_id: UUID,
        db: AsyncSession,
        auto_link_supplier: bool = True,
    ) -> CandidateConversionResult:
        """Convert a candidate to master product.

        Creates ProductMaster + ProductVariant entities from candidate.

        Args:
            candidate_id: Candidate to convert
            db: Database session
            auto_link_supplier: If True, automatically create SupplierOffer from selected SupplierMatch

        Returns:
            CandidateConversionResult with master and variant IDs
        """
        candidate = await db.get(CandidateProduct, candidate_id)
        if not candidate:
            raise ValueError(f"Candidate {candidate_id} not found")

        # Use ProductMasterService to create actual master/variant entities
        result = await self.product_master_service.create_from_candidate(
            candidate_id=candidate_id,
            db=db,
        )

        # Auto-link supplier if requested and this is a new master
        if auto_link_supplier and result.is_new:
            from app.services.supplier_master_service import SupplierMasterService

            supplier_service = SupplierMasterService()
            supplier_result = await supplier_service.resolve_primary_supplier_for_variant(
                variant_id=result.product_variant.id,
                db=db,
            )

            if supplier_result:
                logger.info(
                    "supplier_auto_linked",
                    candidate_id=str(candidate_id),
                    variant_id=str(result.product_variant.id),
                    supplier_id=str(supplier_result.supplier.id),
                    offer_id=str(supplier_result.offer.id),
                    is_new_supplier=supplier_result.is_new_supplier,
                    is_new_offer=supplier_result.is_new_offer,
                )
            else:
                logger.warning(
                    "supplier_auto_link_skipped",
                    candidate_id=str(candidate_id),
                    variant_id=str(result.product_variant.id),
                    reason="no_selected_supplier_match",
                )

        logger.info(
            "candidate_converted_to_master",
            candidate_id=str(candidate_id),
            product_master_id=str(result.product_master.id),
            product_variant_id=str(result.product_variant.id),
            internal_sku=result.product_master.internal_sku,
            is_new=result.is_new,
        )

        return CandidateConversionResult(
            master_candidate_id=candidate_id,
            variant_candidate_ids=[],
            conversion_reason="single_candidate_master",
            is_master=True,
            product_master_id=result.product_master.id,
            product_variant_id=result.product_variant.id,
        )

    async def get_master_candidate(
        self,
        candidate_id: UUID,
        db: AsyncSession,
    ) -> Optional[ProductMaster]:
        """Get ProductMaster linked to a candidate."""
        candidate = await db.get(CandidateProduct, candidate_id)
        if not candidate:
            return None

        master_stmt = select(ProductMaster).where(
            ProductMaster.candidate_product_id == candidate_id
        )
        master_result = await db.execute(master_stmt)
        return master_result.scalar_one_or_none()

    async def validate_conversion_eligibility(
        self,
        candidate_id: UUID,
        db: AsyncSession,
    ) -> tuple[bool, Optional[str]]:
        """Validate if candidate is eligible for master conversion.

        Checks:
        - Candidate exists
        - Has passed pricing assessment (PROFITABLE or MARGINAL)
        - Has passed risk assessment (PASS or REVIEW)

        Args:
            candidate_id: Candidate to validate
            db: Database session

        Returns:
            (eligible, reason) tuple
        """
        candidate = await db.get(CandidateProduct, candidate_id)
        if not candidate:
            return False, "candidate_not_found"

        # Check pricing assessment
        pricing_stmt = select(PricingAssessment).where(
            PricingAssessment.candidate_product_id == candidate_id
        )
        pricing_result = await db.execute(pricing_stmt)
        pricing = pricing_result.scalar_one_or_none()

        if not pricing:
            return False, "no_pricing_assessment"

        from app.core.enums import ProfitabilityDecision

        if pricing.profitability_decision == ProfitabilityDecision.UNPROFITABLE:
            return False, "unprofitable"

        # Check risk assessment
        risk_stmt = select(RiskAssessment).where(
            RiskAssessment.candidate_product_id == candidate_id
        )
        risk_result = await db.execute(risk_stmt)
        risk = risk_result.scalar_one_or_none()

        if not risk:
            return False, "no_risk_assessment"

        from app.core.enums import RiskDecision

        if risk.decision == RiskDecision.REJECT:
            return False, "risk_rejected"

        return True, None
