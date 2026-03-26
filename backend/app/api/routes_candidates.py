"""Candidate product API routes."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Float, cast, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import CandidateProduct
from app.db.session import get_db

router = APIRouter()


@router.get("/candidates")
async def list_candidates(
    sort_by: str = Query("priority", description="Sort by: priority, created_at, margin"),
    db: AsyncSession = Depends(get_db),
):
    """List candidate products.

    Args:
        sort_by: Sort order
            - priority: Sort by priority_score (highest first)
            - created_at: Sort by creation time (newest first)
            - margin: Sort by margin_percentage (highest first)
    """
    query = select(CandidateProduct).options(
        selectinload(CandidateProduct.pricing_assessment),
        selectinload(CandidateProduct.risk_assessment),
        selectinload(CandidateProduct.listing_drafts),
    )

    # Apply sorting
    if sort_by == "priority":
        # Sort by priority_score from normalized_attributes (highest first)
        # Use SQLAlchemy's cross-database JSON accessor for compatibility
        query = query.order_by(
            cast(
                CandidateProduct.normalized_attributes["priority_score"].as_float(),
                Float,
            )
            .desc()
            .nullslast(),
            CandidateProduct.created_at.desc(),
        )
    elif sort_by == "margin":
        # Sort by margin_percentage (highest first)
        # This requires joining with pricing_assessment
        from app.db.models import PricingAssessment

        query = (
            query.outerjoin(PricingAssessment)
            .order_by(PricingAssessment.margin_percentage.desc().nullslast())
        )
    else:  # created_at (default)
        query = query.order_by(CandidateProduct.created_at.desc())

    result = await db.execute(query)
    candidates = result.scalars().all()

    items = []
    for candidate in candidates:
        pricing = candidate.pricing_assessment
        risk = candidate.risk_assessment
        normalized_attrs = candidate.normalized_attributes or {}

        items.append(
            {
                "id": str(candidate.id),
                "title": candidate.title,
                "source_platform": candidate.source_platform.value,
                "platform_price": float(candidate.platform_price)
                if candidate.platform_price
                else None,
                "estimated_margin": float(pricing.estimated_margin)
                if pricing and pricing.estimated_margin is not None
                else None,
                "margin_percentage": float(pricing.margin_percentage)
                if pricing and pricing.margin_percentage is not None
                else None,
                "risk_decision": risk.decision.value if risk else None,
                "risk_score": risk.score if risk else None,
                "status": candidate.status.value,
                "priority_score": normalized_attrs.get("priority_score"),
                "priority_rank": normalized_attrs.get("priority_rank"),
                "seasonal_boost": normalized_attrs.get("seasonal_boost"),
                "created_at": candidate.created_at,
            }
        )

    return {"items": items}


@router.get("/candidates/{candidate_id}")
async def get_candidate(candidate_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get candidate product details."""
    result = await db.execute(
        select(CandidateProduct)
        .where(CandidateProduct.id == candidate_id)
        .options(
            selectinload(CandidateProduct.supplier_matches),
            selectinload(CandidateProduct.pricing_assessment),
            selectinload(CandidateProduct.risk_assessment),
            selectinload(CandidateProduct.listing_drafts),
        )
    )
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    pricing = candidate.pricing_assessment
    risk = candidate.risk_assessment

    return {
        "id": str(candidate.id),
        "strategy_run_id": str(candidate.strategy_run_id),
        "source_platform": candidate.source_platform.value,
        "source_product_id": candidate.source_product_id,
        "source_url": candidate.source_url,
        "title": candidate.title,
        "raw_title": candidate.raw_title,
        "category": candidate.category,
        "currency": candidate.currency,
        "platform_price": float(candidate.platform_price) if candidate.platform_price else None,
        "sales_count": candidate.sales_count,
        "rating": float(candidate.rating) if candidate.rating else None,
        "main_image_url": candidate.main_image_url,
        "normalized_attributes": candidate.normalized_attributes,
        "status": candidate.status.value,
        "pricing_assessment": {
            "estimated_shipping_cost": float(pricing.estimated_shipping_cost) if pricing and pricing.estimated_shipping_cost is not None else None,
            "platform_commission_rate": float(pricing.platform_commission_rate) if pricing and pricing.platform_commission_rate is not None else None,
            "payment_fee_rate": float(pricing.payment_fee_rate) if pricing and pricing.payment_fee_rate is not None else None,
            "return_rate_assumption": float(pricing.return_rate_assumption) if pricing and pricing.return_rate_assumption is not None else None,
            "total_cost": float(pricing.total_cost) if pricing and pricing.total_cost is not None else None,
            "estimated_margin": float(pricing.estimated_margin) if pricing and pricing.estimated_margin is not None else None,
            "margin_percentage": float(pricing.margin_percentage) if pricing and pricing.margin_percentage is not None else None,
            "recommended_price": float(pricing.recommended_price) if pricing and pricing.recommended_price is not None else None,
            "profitability_decision": pricing.profitability_decision.value if pricing and pricing.profitability_decision else None,
            "explanation": pricing.explanation if pricing else None,
        } if pricing else None,
        "risk_assessment": {
            "score": risk.score,
            "decision": risk.decision.value,
            "rule_hits": risk.rule_hits,
            "llm_notes": risk.llm_notes,
        } if risk else None,
        "supplier_matches": [
            {
                "id": str(match.id),
                "supplier_name": match.supplier_name,
                "supplier_url": match.supplier_url,
                "supplier_sku": match.supplier_sku,
                "supplier_price": float(match.supplier_price) if match.supplier_price else None,
                "moq": match.moq,
                "confidence_score": float(match.confidence_score) if match.confidence_score else None,
                "selected": match.selected,
            }
            for match in candidate.supplier_matches
        ],
        "listing_drafts": [
            {
                "id": str(draft.id),
                "language": draft.language,
                "title": draft.title,
                "bullets": draft.bullets or [],
                "description": draft.description,
                "seo_keywords": draft.seo_keywords or [],
                "status": draft.status,
                "prompt_version": draft.prompt_version,
            }
            for draft in candidate.listing_drafts
        ],
        "created_at": candidate.created_at,
    }
