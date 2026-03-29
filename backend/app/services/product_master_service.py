"""Product master and variant management service.

Provides idempotent conversion from CandidateProduct to ProductMaster + ProductVariant,
supporting both the legacy candidate-based pipeline and the new SKU-centric operation.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    InventoryMode,
    ProductLifecycle,
    ProductMasterStatus,
    ProductVariantStatus,
    ProfitabilityDecision,
    RiskDecision,
)
from app.core.logging import get_logger
from app.db.models import (
    CandidateProduct,
    PricingAssessment,
    ProductMaster,
    ProductVariant,
    RiskAssessment,
)

logger = get_logger(__name__)


@dataclass
class ProductMasterResult:
    """Result of creating a product master from a candidate."""

    product_master: ProductMaster
    product_variant: ProductVariant
    conversion_id: str  # stable key used for idempotency
    is_new: bool  # True if new, False if existing was returned


@dataclass
class ConversionEligibility:
    """Eligibility check result for candidate conversion."""

    eligible: bool
    reason: Optional[str]
    pricing_decision: Optional[ProfitabilityDecision]
    risk_decision: Optional[RiskDecision]
    margin_percentage: Optional[Decimal]
    risk_score: Optional[int]


class ProductMasterService:
    """Service for managing product masters and variants."""

    def __init__(self):
        self.logger = get_logger(__name__)

    async def get_eligibility(
        self,
        candidate_id: UUID,
        db: AsyncSession,
    ) -> ConversionEligibility:
        """Check if a candidate is eligible for conversion.

        Returns ConversionEligibility with detailed reasoning.
        """
        candidate = await db.get(CandidateProduct, candidate_id)
        if not candidate:
            return ConversionEligibility(
                eligible=False,
                reason="candidate_not_found",
                pricing_decision=None,
                risk_decision=None,
                margin_percentage=None,
                risk_score=None,
            )

        pricing_stmt = select(PricingAssessment).where(
            PricingAssessment.candidate_product_id == candidate_id
        )
        pricing_result = await db.execute(pricing_stmt)
        pricing = pricing_result.scalar_one_or_none()

        if not pricing:
            return ConversionEligibility(
                eligible=False,
                reason="no_pricing_assessment",
                pricing_decision=None,
                risk_decision=None,
                margin_percentage=None,
                risk_score=None,
            )

        if pricing.profitability_decision == ProfitabilityDecision.UNPROFITABLE:
            return ConversionEligibility(
                eligible=False,
                reason="unprofitable",
                pricing_decision=pricing.profitability_decision,
                risk_decision=None,
                margin_percentage=pricing.margin_percentage,
                risk_score=None,
            )

        risk_stmt = select(RiskAssessment).where(
            RiskAssessment.candidate_product_id == candidate_id
        )
        risk_result = await db.execute(risk_stmt)
        risk = risk_result.scalar_one_or_none()

        if not risk:
            return ConversionEligibility(
                eligible=False,
                reason="no_risk_assessment",
                pricing_decision=pricing.profitability_decision,
                risk_decision=None,
                margin_percentage=pricing.margin_percentage,
                risk_score=None,
            )

        if risk.decision == RiskDecision.REJECT:
            return ConversionEligibility(
                eligible=False,
                reason="risk_rejected",
                pricing_decision=pricing.profitability_decision,
                risk_decision=risk.decision,
                margin_percentage=pricing.margin_percentage,
                risk_score=risk.score,
            )

        return ConversionEligibility(
            eligible=True,
            reason=None,
            pricing_decision=pricing.profitability_decision,
            risk_decision=risk.decision,
            margin_percentage=pricing.margin_percentage,
            risk_score=risk.score,
        )

    def _build_conversion_id(self, candidate_id: UUID) -> str:
        """Build a stable conversion ID for idempotency."""
        return f"candidate_to_master:{candidate_id}"

    def _generate_sku_code(self, candidate_id: UUID, sequence: int = 1) -> str:
        """Generate a unique SKU code."""
        return f"SKU-{candidate_id.hex[:8].upper()}-{sequence:03d}"

    async def _get_or_create_default_variant(
        self,
        product_master: ProductMaster,
        db: AsyncSession,
        inventory_mode: InventoryMode,
    ) -> tuple[ProductVariant, bool]:
        """Return the default variant for a master, creating it if needed."""
        variant_stmt = select(ProductVariant).where(
            ProductVariant.master_id == product_master.id
        ).order_by(ProductVariant.created_at)
        variant_result = await db.execute(variant_stmt)
        existing_variant = variant_result.scalars().first()
        if existing_variant:
            return existing_variant, False

        product_variant = ProductVariant(
            id=uuid4(),
            master_id=product_master.id,
            variant_sku=product_master.internal_sku,
            attributes={},
            inventory_mode=inventory_mode,
            status=ProductVariantStatus.ACTIVE,
        )
        db.add(product_variant)
        await db.flush()
        return product_variant, True

    async def create_from_candidate(
        self,
        candidate_id: UUID,
        db: AsyncSession,
        inventory_mode: Optional[InventoryMode] = None,
    ) -> ProductMasterResult:
        """Create or return existing ProductMaster + default ProductVariant from candidate.

        This method is idempotent: calling it multiple times with the same
        candidate_id returns the same entities without creating duplicates.
        """
        conversion_id = self._build_conversion_id(candidate_id)
        mode = inventory_mode or InventoryMode.STOCK_FIRST

        existing_master_stmt = select(ProductMaster).where(
            ProductMaster.candidate_product_id == candidate_id
        )
        existing_master_result = await db.execute(existing_master_stmt)
        existing_master = existing_master_result.scalar_one_or_none()

        if existing_master:
            existing_variant, created_variant = await self._get_or_create_default_variant(
                existing_master,
                db,
                mode,
            )

            self.logger.info(
                "candidate_already_converted",
                candidate_id=str(candidate_id),
                master_id=str(existing_master.id),
                variant_id=str(existing_variant.id),
                created_missing_variant=created_variant,
            )

            await db.commit()
            await db.refresh(existing_master)
            await db.refresh(existing_variant)

            return ProductMasterResult(
                product_master=existing_master,
                product_variant=existing_variant,
                conversion_id=conversion_id,
                is_new=False,
            )

        candidate = await db.get(CandidateProduct, candidate_id)
        if not candidate:
            raise ValueError(f"Candidate {candidate_id} not found")

        sku_code = self._generate_sku_code(candidate_id)

        product_master = ProductMaster(
            id=uuid4(),
            candidate_product_id=candidate_id,
            internal_sku=sku_code,
            name=candidate.title,
            category=candidate.category,
            description=None,
            status=ProductMasterStatus.ACTIVE,
        )
        db.add(product_master)
        await db.flush()

        product_variant, _ = await self._get_or_create_default_variant(
            product_master,
            db,
            mode,
        )

        candidate.internal_sku = sku_code
        candidate.lifecycle_status = ProductLifecycle.APPROVED

        await db.commit()
        await db.refresh(product_master)
        await db.refresh(product_variant)

        self.logger.info(
            "candidate_converted_to_master",
            candidate_id=str(candidate_id),
            master_id=str(product_master.id),
            variant_id=str(product_variant.id),
            sku_code=sku_code,
            inventory_mode=mode.value,
        )

        return ProductMasterResult(
            product_master=product_master,
            product_variant=product_variant,
            conversion_id=conversion_id,
            is_new=True,
        )

    async def get_master_by_candidate(
        self,
        candidate_id: UUID,
        db: AsyncSession,
    ) -> Optional[ProductMaster]:
        """Get ProductMaster linked to a candidate."""
        stmt = select(ProductMaster).where(
            ProductMaster.candidate_product_id == candidate_id
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_variant_by_id(
        self,
        variant_id: UUID,
        db: AsyncSession,
    ) -> Optional[ProductVariant]:
        """Get ProductVariant by ID."""
        return await db.get(ProductVariant, variant_id)

    async def get_variant_by_sku(
        self,
        sku_code: str,
        db: AsyncSession,
    ) -> Optional[ProductVariant]:
        """Get ProductVariant by SKU code."""
        stmt = select(ProductVariant).where(ProductVariant.variant_sku == sku_code)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_variants_for_master(
        self,
        master_id: UUID,
        db: AsyncSession,
    ) -> list[ProductVariant]:
        """List all variants for a product master."""
        stmt = select(ProductVariant).where(
            ProductVariant.master_id == master_id
        ).order_by(ProductVariant.created_at)
        result = await db.execute(stmt)
        return list(result.scalars().all())
