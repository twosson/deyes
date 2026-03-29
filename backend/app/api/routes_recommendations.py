"""Recommendation API routes."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import FeedbackAction, RiskDecision
from app.db.models import CandidateProduct, RecommendationFeedback
from app.db.session import get_db
from app.schemas.feedback import CreateFeedbackRequest, FeedbackResponse
from app.services.recommendation_feedback_service import RecommendationFeedbackService
from app.services.recommendation_service import RecommendationService

router = APIRouter()
recommendation_service = RecommendationService()
feedback_service = RecommendationFeedbackService()


@router.get("/recommendations")
async def list_recommendations(
    limit: int = Query(20, ge=1, le=100, description="Maximum number of recommendations"),
    category: Optional[str] = Query(None, description="Filter by category"),
    min_score: float = Query(60.0, ge=0, le=100, description="Minimum recommendation score"),
    risk_level: Optional[str] = Query(
        None, description="Filter by risk level: PASS, REVIEW, REJECT"
    ),
    db: AsyncSession = Depends(get_db),
):
    """Get recommended candidate products.

    Returns candidates sorted by recommendation score (highest first).

    Args:
        limit: Maximum number of recommendations to return (1-100)
        category: Optional category filter
        min_score: Minimum recommendation score (0-100)
        risk_level: Optional risk level filter (PASS/REVIEW/REJECT)
        db: Database session

    Returns:
        List of recommended candidates with scores and reasons
    """
    # Build query
    query = select(CandidateProduct).options(
        selectinload(CandidateProduct.pricing_assessment),
        selectinload(CandidateProduct.risk_assessment),
        selectinload(CandidateProduct.supplier_matches),
    )

    # Apply category filter
    if category:
        query = query.where(CandidateProduct.category == category)

    # Apply risk level filter
    if risk_level:
        try:
            risk_decision = RiskDecision(risk_level.lower())
            from app.db.models import RiskAssessment

            query = query.join(RiskAssessment).where(RiskAssessment.decision == risk_decision)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid risk_level: {risk_level}. Must be PASS, REVIEW, or REJECT",
            )

    # Execute query
    result = await db.execute(query)
    candidates = result.scalars().all()

    # Calculate recommendation scores for all candidates
    recommendations = []
    for candidate in candidates:
        pricing = candidate.pricing_assessment
        risk = candidate.risk_assessment
        normalized_attrs = candidate.normalized_attributes or {}
        demand_metadata = candidate.demand_discovery_metadata or {}

        # Get best supplier confidence
        supplier_confidence = None
        if candidate.supplier_matches:
            confidences = [
                match.confidence_score
                for match in candidate.supplier_matches
                if match.confidence_score is not None
            ]
            if confidences:
                supplier_confidence = max(confidences)

        # Calculate recommendation score
        score, breakdown = recommendation_service.calculate_recommendation_score(
            priority_score=normalized_attrs.get("priority_score"),
            margin_percentage=pricing.margin_percentage if pricing else None,
            risk_score=risk.score if risk else None,
            supplier_confidence=supplier_confidence,
            discovery_mode=demand_metadata.get("discovery_mode"),
            degraded=bool(demand_metadata.get("degraded", False)),
            fallback_used=bool(demand_metadata.get("fallback_used", False)),
        )

        # Filter by min_score
        if score < min_score:
            continue

        # Generate recommendation reasons
        reasons = recommendation_service.generate_recommendation_reasons(
            margin_percentage=pricing.margin_percentage if pricing else None,
            seasonal_boost=normalized_attrs.get("seasonal_boost"),
            competition_density=normalized_attrs.get("competition_density"),
            risk_decision=risk.decision if risk else None,
            sales_count=candidate.sales_count,
            rating=candidate.rating,
            profitability_decision=pricing.profitability_decision if pricing else None,
            discovery_mode=demand_metadata.get("discovery_mode"),
            degraded=bool(demand_metadata.get("degraded", False)),
            fallback_used=bool(demand_metadata.get("fallback_used", False)),
        )

        # Get recommendation level
        level = recommendation_service.get_recommendation_level(score)

        recommendations.append(
            {
                "candidate_id": str(candidate.id),
                "title": candidate.title,
                "category": candidate.category,
                "source_platform": candidate.source_platform.value,
                "platform_price": float(candidate.platform_price)
                if candidate.platform_price
                else None,
                "recommendation_score": round(score, 2),
                "recommendation_level": level,
                "reasons": reasons,
                "score_breakdown": breakdown,
                "priority_score": normalized_attrs.get("priority_score"),
                "margin_percentage": float(pricing.margin_percentage)
                if pricing and pricing.margin_percentage
                else None,
                "risk_decision": risk.decision.value if risk else None,
                "risk_score": risk.score if risk else None,
                "created_at": candidate.created_at,
            }
        )

    # Sort by recommendation score (highest first)
    recommendations.sort(key=lambda x: x["recommendation_score"], reverse=True)

    # Apply limit
    recommendations = recommendations[:limit]

    return {
        "items": recommendations,
        "count": len(recommendations),
        "filters": {
            "category": category,
            "min_score": min_score,
            "risk_level": risk_level,
        },
    }


@router.get("/candidates/{candidate_id}/recommendation")
async def get_candidate_recommendation(
    candidate_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get recommendation details for a specific candidate.

    Args:
        candidate_id: Candidate product ID
        db: Database session

    Returns:
        Detailed recommendation with score breakdown and reasons
    """
    # Fetch candidate with relationships
    result = await db.execute(
        select(CandidateProduct)
        .where(CandidateProduct.id == candidate_id)
        .options(
            selectinload(CandidateProduct.pricing_assessment),
            selectinload(CandidateProduct.risk_assessment),
            selectinload(CandidateProduct.supplier_matches),
        )
    )
    candidate = result.scalar_one_or_none()

    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    pricing = candidate.pricing_assessment
    risk = candidate.risk_assessment
    normalized_attrs = candidate.normalized_attributes or {}
    demand_metadata = candidate.demand_discovery_metadata or {}

    # Get best supplier confidence
    supplier_confidence = None
    best_supplier = None
    if candidate.supplier_matches:
        confidences = [
            (match.confidence_score, match)
            for match in candidate.supplier_matches
            if match.confidence_score is not None
        ]
        if confidences:
            supplier_confidence, best_supplier = max(confidences, key=lambda x: x[0])

    # Calculate recommendation score
    score, breakdown = recommendation_service.calculate_recommendation_score(
        priority_score=normalized_attrs.get("priority_score"),
        margin_percentage=pricing.margin_percentage if pricing else None,
        risk_score=risk.score if risk else None,
        supplier_confidence=supplier_confidence,
        discovery_mode=demand_metadata.get("discovery_mode"),
        degraded=bool(demand_metadata.get("degraded", False)),
        fallback_used=bool(demand_metadata.get("fallback_used", False)),
    )

    # Generate recommendation reasons
    reasons = recommendation_service.generate_recommendation_reasons(
        margin_percentage=pricing.margin_percentage if pricing else None,
        seasonal_boost=normalized_attrs.get("seasonal_boost"),
        competition_density=normalized_attrs.get("competition_density"),
        risk_decision=risk.decision if risk else None,
        sales_count=candidate.sales_count,
        rating=candidate.rating,
        profitability_decision=pricing.profitability_decision if pricing else None,
        discovery_mode=demand_metadata.get("discovery_mode"),
        degraded=bool(demand_metadata.get("degraded", False)),
        fallback_used=bool(demand_metadata.get("fallback_used", False)),
    )

    # Get recommendation level
    level = recommendation_service.get_recommendation_level(score)

    # Explain score breakdown
    explained_breakdown = recommendation_service.explain_score_breakdown(breakdown)

    return {
        "candidate_id": str(candidate.id),
        "title": candidate.title,
        "category": candidate.category,
        "source_platform": candidate.source_platform.value,
        "source_url": candidate.source_url,
        "platform_price": float(candidate.platform_price) if candidate.platform_price else None,
        "sales_count": candidate.sales_count,
        "rating": float(candidate.rating) if candidate.rating else None,
        "recommendation": {
            "score": round(score, 2),
            "level": level,
            "reasons": reasons,
            "score_breakdown": explained_breakdown,
        },
        "pricing_summary": {
            "margin_percentage": float(pricing.margin_percentage)
            if pricing and pricing.margin_percentage
            else None,
            "profitability_decision": pricing.profitability_decision.value if pricing else None,
            "recommended_price": float(pricing.recommended_price)
            if pricing and pricing.recommended_price
            else None,
        }
        if pricing
        else None,
        "risk_summary": {
            "score": risk.score,
            "decision": risk.decision.value,
            "rule_hits": risk.rule_hits,
        }
        if risk
        else None,
        "best_supplier": {
            "supplier_name": best_supplier.supplier_name,
            "supplier_price": float(best_supplier.supplier_price)
            if best_supplier.supplier_price
            else None,
            "confidence_score": float(best_supplier.confidence_score)
            if best_supplier.confidence_score
            else None,
            "moq": best_supplier.moq,
        }
        if best_supplier
        else None,
        "normalized_attributes": normalized_attrs,
        "created_at": candidate.created_at,
    }


@router.post("/recommendations/{candidate_id}/feedback", response_model=FeedbackResponse)
async def create_recommendation_feedback(
    candidate_id: UUID,
    payload: CreateFeedbackRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create user feedback for a recommendation."""
    result = await db.execute(
        select(CandidateProduct)
        .where(CandidateProduct.id == candidate_id)
        .options(
            selectinload(CandidateProduct.pricing_assessment),
            selectinload(CandidateProduct.risk_assessment),
            selectinload(CandidateProduct.supplier_matches),
        )
    )
    candidate = result.scalar_one_or_none()

    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    pricing = candidate.pricing_assessment
    risk = candidate.risk_assessment
    normalized_attrs = candidate.normalized_attributes or {}
    demand_metadata = candidate.demand_discovery_metadata or {}

    supplier_confidence = None
    if candidate.supplier_matches:
        confidences = [
            match.confidence_score
            for match in candidate.supplier_matches
            if match.confidence_score is not None
        ]
        if confidences:
            supplier_confidence = max(confidences)

    score, _ = recommendation_service.calculate_recommendation_score(
        priority_score=normalized_attrs.get("priority_score"),
        margin_percentage=pricing.margin_percentage if pricing else None,
        risk_score=risk.score if risk else None,
        supplier_confidence=supplier_confidence,
        discovery_mode=demand_metadata.get("discovery_mode"),
        degraded=bool(demand_metadata.get("degraded", False)),
        fallback_used=bool(demand_metadata.get("fallback_used", False)),
    )
    level = recommendation_service.get_recommendation_level(score)

    feedback = await feedback_service.create_feedback(
        db=db,
        candidate=candidate,
        action=payload.action,
        comment=payload.comment,
        metadata={
            "recommendation_score": round(score, 2),
            "recommendation_level": level,
            "source_platform": candidate.source_platform.value,
        },
    )

    return feedback


@router.get("/recommendations/stats/trends")
async def get_recommendation_trends(
    period: str = Query("day", description="Aggregation period: day, week, month"),
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    min_score: float = Query(60.0, ge=0, le=100, description="Minimum recommendation score"),
    db: AsyncSession = Depends(get_db),
):
    """Get recommendation time series trends.

    Returns time-series data showing recommendation counts and average scores over time.

    Args:
        period: Aggregation period (day/week/month)
        days: Number of days to look back (1-365)
        min_score: Minimum recommendation score to include
        db: Database session

    Returns:
        Time series data with counts and average scores
    """
    from datetime import datetime, timedelta, timezone

    # Calculate date range
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    # Fetch candidates in date range
    query = (
        select(CandidateProduct)
        .where(CandidateProduct.created_at >= start_date)
        .where(CandidateProduct.created_at <= end_date)
        .options(
            selectinload(CandidateProduct.pricing_assessment),
            selectinload(CandidateProduct.risk_assessment),
            selectinload(CandidateProduct.supplier_matches),
        )
    )

    result = await db.execute(query)
    candidates = result.scalars().all()

    # Calculate recommendation scores and group by date
    from collections import defaultdict

    trends_data = defaultdict(lambda: {"count": 0, "total_score": 0.0, "scores": []})

    for candidate in candidates:
        pricing = candidate.pricing_assessment
        risk = candidate.risk_assessment
        normalized_attrs = candidate.normalized_attributes or {}
        demand_metadata = candidate.demand_discovery_metadata or {}

        # Get best supplier confidence
        supplier_confidence = None
        if candidate.supplier_matches:
            confidences = [
                match.confidence_score
                for match in candidate.supplier_matches
                if match.confidence_score is not None
            ]
            if confidences:
                supplier_confidence = max(confidences)

        # Calculate recommendation score
        score, _ = recommendation_service.calculate_recommendation_score(
            priority_score=normalized_attrs.get("priority_score"),
            margin_percentage=pricing.margin_percentage if pricing else None,
            risk_score=risk.score if risk else None,
            supplier_confidence=supplier_confidence,
            discovery_mode=demand_metadata.get("discovery_mode"),
            degraded=bool(demand_metadata.get("degraded", False)),
            fallback_used=bool(demand_metadata.get("fallback_used", False)),
        )

        # Filter by min_score
        if score < min_score:
            continue

        # Determine date bucket
        created_date = candidate.created_at
        if period == "day":
            date_key = created_date.strftime("%Y-%m-%d")
        elif period == "week":
            # ISO week format
            date_key = created_date.strftime("%Y-W%W")
        elif period == "month":
            date_key = created_date.strftime("%Y-%m")
        else:
            date_key = created_date.strftime("%Y-%m-%d")

        trends_data[date_key]["count"] += 1
        trends_data[date_key]["total_score"] += score
        trends_data[date_key]["scores"].append(score)

    # Convert to list format with average scores
    trends_list = []
    for date_key in sorted(trends_data.keys()):
        data = trends_data[date_key]
        avg_score = data["total_score"] / data["count"] if data["count"] > 0 else 0.0
        trends_list.append(
            {
                "date": date_key,
                "count": data["count"],
                "average_score": round(avg_score, 2),
            }
        )

    return {
        "period": period,
        "days": days,
        "min_score": min_score,
        "data": trends_list,
    }


@router.get("/recommendations/stats/by-platform")
async def get_recommendations_by_platform(
    min_score: float = Query(60.0, ge=0, le=100, description="Minimum recommendation score"),
    db: AsyncSession = Depends(get_db),
):
    """Get recommendation statistics grouped by source platform.

    Returns aggregated statistics comparing different source platforms.

    Args:
        min_score: Minimum recommendation score to include
        db: Database session

    Returns:
        Platform comparison data with counts and average scores
    """
    # Fetch all candidates
    query = select(CandidateProduct).options(
        selectinload(CandidateProduct.pricing_assessment),
        selectinload(CandidateProduct.risk_assessment),
        selectinload(CandidateProduct.supplier_matches),
    )

    result = await db.execute(query)
    candidates = result.scalars().all()

    # Calculate recommendation scores and group by platform
    from collections import defaultdict

    platform_data = defaultdict(lambda: {"count": 0, "total_score": 0.0, "scores": []})

    for candidate in candidates:
        pricing = candidate.pricing_assessment
        risk = candidate.risk_assessment
        normalized_attrs = candidate.normalized_attributes or {}
        demand_metadata = candidate.demand_discovery_metadata or {}

        # Get best supplier confidence
        supplier_confidence = None
        if candidate.supplier_matches:
            confidences = [
                match.confidence_score
                for match in candidate.supplier_matches
                if match.confidence_score is not None
            ]
            if confidences:
                supplier_confidence = max(confidences)

        # Calculate recommendation score
        score, _ = recommendation_service.calculate_recommendation_score(
            priority_score=normalized_attrs.get("priority_score"),
            margin_percentage=pricing.margin_percentage if pricing else None,
            risk_score=risk.score if risk else None,
            supplier_confidence=supplier_confidence,
            discovery_mode=demand_metadata.get("discovery_mode"),
            degraded=bool(demand_metadata.get("degraded", False)),
            fallback_used=bool(demand_metadata.get("fallback_used", False)),
        )

        # Filter by min_score
        if score < min_score:
            continue

        platform = candidate.source_platform.value
        platform_data[platform]["count"] += 1
        platform_data[platform]["total_score"] += score
        platform_data[platform]["scores"].append(score)

    # Convert to list format with statistics
    platform_list = []
    for platform, data in platform_data.items():
        avg_score = data["total_score"] / data["count"] if data["count"] > 0 else 0.0
        high_quality_count = sum(1 for s in data["scores"] if s >= 75)
        platform_list.append(
            {
                "platform": platform,
                "count": data["count"],
                "average_score": round(avg_score, 2),
                "high_quality_count": high_quality_count,
                "high_quality_percentage": round(
                    (high_quality_count / data["count"]) * 100, 2
                )
                if data["count"] > 0
                else 0.0,
            }
        )

    # Sort by count descending
    platform_list.sort(key=lambda x: x["count"], reverse=True)

    return {
        "min_score": min_score,
        "data": platform_list,
    }


@router.get("/recommendations/stats/feedback")
async def get_recommendation_feedback_stats(
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    db: AsyncSession = Depends(get_db),
):
    """Get user feedback statistics on recommendations.

    Returns aggregated statistics about user feedback actions.

    Args:
        days: Number of days to look back (1-365)
        db: Database session

    Returns:
        Feedback statistics grouped by action type
    """
    from datetime import datetime, timedelta, timezone

    # Calculate date range
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    # Fetch feedback in date range
    query = (
        select(RecommendationFeedback)
        .where(RecommendationFeedback.created_at >= start_date)
        .where(RecommendationFeedback.created_at <= end_date)
    )

    result = await db.execute(query)
    feedbacks = result.scalars().all()

    # Aggregate by action type
    from collections import defaultdict

    action_counts = defaultdict(int)
    for feedback in feedbacks:
        action_counts[feedback.action.value] += 1

    # Convert to list format
    feedback_list = [
        {"action": action, "count": count} for action, count in action_counts.items()
    ]

    # Sort by count descending
    feedback_list.sort(key=lambda x: x["count"], reverse=True)

    return {
        "days": days,
        "total_feedback": len(feedbacks),
        "data": feedback_list,
    }


@router.get("/recommendations/stats/overview")
async def get_recommendation_stats(
    min_score: float = Query(60.0, ge=0, le=100, description="Minimum recommendation score"),
    db: AsyncSession = Depends(get_db),
):
    """Get recommendation statistics overview.

    Returns aggregated statistics about recommendations including:
    - Distribution by recommendation level (HIGH/MEDIUM/LOW)
    - Distribution by category
    - Score distribution histogram
    - Margin vs Score scatter plot data
    - Average score and high quality metrics

    Args:
        min_score: Minimum recommendation score to include (default 60.0)
        db: Database session

    Returns:
        Dictionary with stats aggregations
    """
    # Fetch all candidates with relationships
    query = select(CandidateProduct).options(
        selectinload(CandidateProduct.pricing_assessment),
        selectinload(CandidateProduct.risk_assessment),
        selectinload(CandidateProduct.supplier_matches),
    )

    result = await db.execute(query)
    candidates = result.scalars().all()

    # Calculate recommendation scores for all candidates
    recommendations = []
    for candidate in candidates:
        pricing = candidate.pricing_assessment
        risk = candidate.risk_assessment
        normalized_attrs = candidate.normalized_attributes or {}
        demand_metadata = candidate.demand_discovery_metadata or {}

        # Get best supplier confidence
        supplier_confidence = None
        if candidate.supplier_matches:
            confidences = [
                match.confidence_score
                for match in candidate.supplier_matches
                if match.confidence_score is not None
            ]
            if confidences:
                supplier_confidence = max(confidences)

        # Calculate recommendation score
        score, breakdown = recommendation_service.calculate_recommendation_score(
            priority_score=normalized_attrs.get("priority_score"),
            margin_percentage=pricing.margin_percentage if pricing else None,
            risk_score=risk.score if risk else None,
            supplier_confidence=supplier_confidence,
            discovery_mode=demand_metadata.get("discovery_mode"),
            degraded=bool(demand_metadata.get("degraded", False)),
            fallback_used=bool(demand_metadata.get("fallback_used", False)),
        )

        # Filter by min_score
        if score < min_score:
            continue

        # Get recommendation level
        level = recommendation_service.get_recommendation_level(score)

        recommendations.append(
            {
                "score": score,
                "level": level,
                "category": candidate.category,
                "margin_percentage": float(pricing.margin_percentage)
                if pricing and pricing.margin_percentage
                else None,
            }
        )

    # Calculate average score and high quality metrics from filtered recommendations
    average_score = (
        round(sum(r["score"] for r in recommendations) / len(recommendations), 2)
        if recommendations
        else 0.0
    )
    high_quality_count = sum(1 for r in recommendations if r["score"] >= 75)
    high_quality_percentage = (
        round((high_quality_count / len(recommendations)) * 100, 2) if recommendations else 0.0
    )

    # Aggregate by level
    by_level = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for rec in recommendations:
        by_level[rec["level"]] += 1

    # Aggregate by category
    by_category = {}
    for rec in recommendations:
        category = rec["category"] or "unknown"
        by_category[category] = by_category.get(category, 0) + 1

    # Score distribution (10-point buckets: 0-10, 10-20, ..., 90-100)
    score_distribution_dict = {f"{i}-{i+10}": 0 for i in range(0, 100, 10)}
    for rec in recommendations:
        score = rec["score"]
        bucket_start = int(score // 10) * 10
        if bucket_start >= 90:
            bucket_start = 90
        bucket_key = f"{bucket_start}-{bucket_start+10}"
        score_distribution_dict[bucket_key] += 1

    # Convert to list format
    score_distribution = [
        {"range": range_key, "count": count}
        for range_key, count in score_distribution_dict.items()
    ]

    # Margin vs Score scatter plot (limit to 100 points for performance)
    margin_vs_score = []
    for rec in recommendations[:100]:
        if rec["margin_percentage"] is not None:
            margin_vs_score.append(
                {
                    "score": round(rec["score"], 2),
                    "margin": round(rec["margin_percentage"], 2),
                    "category": rec["category"] or "unknown",
                }
            )

    return {
        "total_recommendations": len(recommendations),
        "average_score": average_score,
        "high_quality_count": high_quality_count,
        "high_quality_percentage": high_quality_percentage,
        "by_level": by_level,
        "by_category": by_category,
        "score_distribution": score_distribution,
        "margin_vs_score": margin_vs_score,
    }

