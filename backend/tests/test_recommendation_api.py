"""Tests for recommendation API endpoints."""
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    CandidateStatus,
    ProfitabilityDecision,
    RiskDecision,
    SourcePlatform,
    StrategyRunStatus,
    TriggerType,
)
from app.db.models import (
    CandidateProduct,
    PricingAssessment,
    RiskAssessment,
    StrategyRun,
    SupplierMatch,
)
from app.db.session import get_db
from app.main import app


async def _create_test_candidate(
    db_session: AsyncSession,
    *,
    title: str = "Test Product",
    category: str = "electronics",
    platform_price: Decimal = Decimal("50.00"),
    sales_count: int = 1000,
    rating: Decimal = Decimal("4.5"),
    priority_score: float = 0.7,
    seasonal_boost: float = 1.2,
    competition_density: str = "low",
) -> CandidateProduct:
    """Create a test candidate with all relationships."""
    # Create strategy run
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.TEMU,
        status=StrategyRunStatus.COMPLETED,
        max_candidates=10,
    )
    db_session.add(strategy_run)
    await db_session.flush()

    # Create candidate
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.TEMU,
        source_product_id="test-123",
        source_url="https://example.com/product/123",
        title=title,
        category=category,
        platform_price=platform_price,
        sales_count=sales_count,
        rating=rating,
        status=CandidateStatus.DISCOVERED,
        normalized_attributes={
            "priority_score": priority_score,
            "seasonal_boost": seasonal_boost,
            "competition_density": competition_density,
        },
    )
    db_session.add(candidate)
    await db_session.flush()

    return candidate


async def _add_pricing_assessment(
    db_session: AsyncSession,
    candidate_id,
    *,
    margin_percentage: Decimal = Decimal("35.0"),
    profitability_decision: ProfitabilityDecision = ProfitabilityDecision.PROFITABLE,
) -> PricingAssessment:
    """Add pricing assessment to candidate."""
    pricing = PricingAssessment(
        id=uuid4(),
        candidate_product_id=candidate_id,
        estimated_shipping_cost=Decimal("5.00"),
        platform_commission_rate=Decimal("0.10"),
        payment_fee_rate=Decimal("0.02"),
        return_rate_assumption=Decimal("0.05"),
        total_cost=Decimal("30.00"),
        estimated_margin=Decimal("20.00"),
        margin_percentage=margin_percentage,
        recommended_price=Decimal("55.00"),
        profitability_decision=profitability_decision,
    )
    db_session.add(pricing)
    await db_session.flush()
    return pricing


async def _add_risk_assessment(
    db_session: AsyncSession,
    candidate_id,
    *,
    score: int = 20,
    decision: RiskDecision = RiskDecision.PASS,
) -> RiskAssessment:
    """Add risk assessment to candidate."""
    risk = RiskAssessment(
        id=uuid4(),
        candidate_product_id=candidate_id,
        score=score,
        decision=decision,
        rule_hits=[{"rule": "competition_density", "weight": 20, "reason": "Low competition"}],
    )
    db_session.add(risk)
    await db_session.flush()
    return risk


async def _add_supplier_match(
    db_session: AsyncSession,
    candidate_id,
    *,
    confidence_score: Decimal = Decimal("0.85"),
) -> SupplierMatch:
    """Add supplier match to candidate."""
    supplier = SupplierMatch(
        id=uuid4(),
        candidate_product_id=candidate_id,
        supplier_name="Test Supplier",
        supplier_url="https://1688.com/supplier/123",
        supplier_sku="SKU-123",
        supplier_price=Decimal("25.00"),
        moq=100,
        confidence_score=confidence_score,
        selected=True,
    )
    db_session.add(supplier)
    await db_session.flush()
    return supplier


@pytest.mark.asyncio
async def test_list_recommendations(db_session):
    """Test listing recommendations."""
    # Override get_db dependency to use test db_session
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        # Create test candidates with different quality levels
        # High quality candidate
        candidate1 = await _create_test_candidate(
            db_session,
            title="High Quality Product",
            priority_score=0.9,
            sales_count=5000,
            rating=Decimal("4.8"),
        )
        await _add_pricing_assessment(
            db_session, candidate1.id, margin_percentage=Decimal("45.0")
        )
        await _add_risk_assessment(db_session, candidate1.id, score=10)
        await _add_supplier_match(db_session, candidate1.id, confidence_score=Decimal("0.95"))

        # Medium quality candidate
        candidate2 = await _create_test_candidate(
            db_session,
            title="Medium Quality Product",
            priority_score=0.6,
            sales_count=1000,
            rating=Decimal("4.2"),
        )
        await _add_pricing_assessment(
            db_session, candidate2.id, margin_percentage=Decimal("30.0")
        )
        await _add_risk_assessment(db_session, candidate2.id, score=40)
        await _add_supplier_match(db_session, candidate2.id, confidence_score=Decimal("0.7"))

        # Low quality candidate (below min_score)
        candidate3 = await _create_test_candidate(
            db_session,
            title="Low Quality Product",
            priority_score=0.2,
            sales_count=50,
            rating=Decimal("3.5"),
        )
        await _add_pricing_assessment(
            db_session,
            candidate3.id,
            margin_percentage=Decimal("15.0"),
            profitability_decision=ProfitabilityDecision.UNPROFITABLE,
        )
        await _add_risk_assessment(db_session, candidate3.id, score=80, decision=RiskDecision.REJECT)
        await _add_supplier_match(db_session, candidate3.id, confidence_score=Decimal("0.3"))

        await db_session.commit()

        # Test API
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/recommendations?limit=10&min_score=60")
            assert response.status_code == 200

            data = response.json()
            assert "items" in data
            assert "count" in data

            # Should return 2 candidates (high and medium quality, low quality filtered out)
            # Actually, let me recalculate:
            # High: 0.9*40 + 0.45*30 + 0.9*20 + 0.95*10 = 36 + 13.5 + 18 + 9.5 = 77
            # Medium: 0.6*40 + 0.30*30 + 0.6*20 + 0.7*10 = 24 + 9 + 12 + 7 = 52
            # Low: 0.2*40 + 0.15*30 + 0.2*20 + 0.3*10 = 8 + 4.5 + 4 + 3 = 19.5

            # With min_score=60, only high quality should pass
            assert data["count"] == 1
            assert data["items"][0]["title"] == "High Quality Product"
            assert data["items"][0]["recommendation_score"] >= 75.0
            assert data["items"][0]["recommendation_level"] == "HIGH"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_recommendations_with_filters(db_session):
    """Test listing recommendations with category and risk filters."""
    # Override get_db dependency
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        # Create candidates in different categories
        candidate1 = await _create_test_candidate(
            db_session,
            title="Electronics Product",
            category="electronics",
            priority_score=0.8,
        )
        await _add_pricing_assessment(db_session, candidate1.id, margin_percentage=Decimal("40.0"))
        await _add_risk_assessment(db_session, candidate1.id, score=15, decision=RiskDecision.PASS)
        await _add_supplier_match(db_session, candidate1.id)

        candidate2 = await _create_test_candidate(
            db_session,
            title="Home Product",
            category="home",
            priority_score=0.8,
        )
        await _add_pricing_assessment(db_session, candidate2.id, margin_percentage=Decimal("40.0"))
        await _add_risk_assessment(db_session, candidate2.id, score=45, decision=RiskDecision.REVIEW)
        await _add_supplier_match(db_session, candidate2.id)

        await db_session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Test category filter
            response = await client.get("/api/v1/recommendations?category=electronics")
            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 1
            assert data["items"][0]["category"] == "electronics"

            # Test risk level filter
            response = await client.get("/api/v1/recommendations?risk_level=PASS")
            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 1
            assert data["items"][0]["risk_decision"] == "pass"  # API returns lowercase enum value
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_candidate_recommendation(db_session):
    """Test getting recommendation for a specific candidate."""
    # Override get_db dependency
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        # Create test candidate
        candidate = await _create_test_candidate(
            db_session,
            title="Test Product",
            priority_score=0.75,
            sales_count=2000,
            rating=Decimal("4.6"),
        )
        await _add_pricing_assessment(db_session, candidate.id, margin_percentage=Decimal("38.0"))
        await _add_risk_assessment(db_session, candidate.id, score=25)
        await _add_supplier_match(db_session, candidate.id, confidence_score=Decimal("0.88"))

        await db_session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v1/candidates/{candidate.id}/recommendation")
            assert response.status_code == 200

            data = response.json()
            assert data["candidate_id"] == str(candidate.id)
            assert data["title"] == "Test Product"

            # Check recommendation section
            assert "recommendation" in data
            rec = data["recommendation"]
            assert "score" in rec
            assert "level" in rec
            assert "reasons" in rec
            assert "score_breakdown" in rec

            # Check score breakdown has components
            breakdown = rec["score_breakdown"]
            assert "total_score" in breakdown
            assert "components" in breakdown
            assert len(breakdown["components"]) == 4

            # Check pricing summary
            assert "pricing_summary" in data
            assert data["pricing_summary"]["margin_percentage"] == 38.0

            # Check risk summary
            assert "risk_summary" in data
            assert data["risk_summary"]["score"] == 25

            # Check best supplier
            assert "best_supplier" in data
            assert data["best_supplier"]["confidence_score"] == 0.88
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_candidate_recommendation_not_found(db_session):
    """Test getting recommendation for non-existent candidate."""
    # Override get_db dependency
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        await db_session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            fake_id = uuid4()
            response = await client.get(f"/api/v1/candidates/{fake_id}/recommendation")
            assert response.status_code == 404
            assert response.json()["detail"] == "Candidate not found"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_recommendations_invalid_risk_level(db_session):
    """Test listing recommendations with invalid risk level."""
    # Override get_db dependency
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        await db_session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/recommendations?risk_level=INVALID")
            assert response.status_code == 400
            assert "Invalid risk_level" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_recommendation_stats_overview(db_session):
    """Test getting recommendation statistics overview."""
    # Override get_db dependency
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        # Create diverse test candidates
        # High quality electronics
        candidate1 = await _create_test_candidate(
            db_session,
            title="High Quality Electronics",
            category="electronics",
            priority_score=0.9,
            sales_count=5000,
            rating=Decimal("4.8"),
        )
        await _add_pricing_assessment(
            db_session, candidate1.id, margin_percentage=Decimal("45.0")
        )
        await _add_risk_assessment(db_session, candidate1.id, score=10)
        await _add_supplier_match(db_session, candidate1.id, confidence_score=Decimal("0.95"))

        # Medium quality home
        candidate2 = await _create_test_candidate(
            db_session,
            title="Medium Quality Home",
            category="home",
            priority_score=0.6,
            sales_count=1000,
            rating=Decimal("4.2"),
        )
        await _add_pricing_assessment(
            db_session, candidate2.id, margin_percentage=Decimal("30.0")
        )
        await _add_risk_assessment(db_session, candidate2.id, score=40)
        await _add_supplier_match(db_session, candidate2.id, confidence_score=Decimal("0.7"))

        # Low quality electronics
        candidate3 = await _create_test_candidate(
            db_session,
            title="Low Quality Electronics",
            category="electronics",
            priority_score=0.2,
            sales_count=50,
            rating=Decimal("3.5"),
        )
        await _add_pricing_assessment(
            db_session,
            candidate3.id,
            margin_percentage=Decimal("15.0"),
            profitability_decision=ProfitabilityDecision.UNPROFITABLE,
        )
        await _add_risk_assessment(db_session, candidate3.id, score=80, decision=RiskDecision.REJECT)
        await _add_supplier_match(db_session, candidate3.id, confidence_score=Decimal("0.3"))

        # Another high quality home
        candidate4 = await _create_test_candidate(
            db_session,
            title="High Quality Home",
            category="home",
            priority_score=0.85,
            sales_count=3000,
            rating=Decimal("4.7"),
        )
        await _add_pricing_assessment(
            db_session, candidate4.id, margin_percentage=Decimal("42.0")
        )
        await _add_risk_assessment(db_session, candidate4.id, score=15)
        await _add_supplier_match(db_session, candidate4.id, confidence_score=Decimal("0.9"))

        await db_session.commit()

        # Test API
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/recommendations/stats/overview")
            assert response.status_code == 200

            data = response.json()

            # Check structure
            assert "total_recommendations" in data
            assert "average_score" in data
            assert "high_quality_count" in data
            assert "high_quality_percentage" in data
            assert "by_level" in data
            assert "by_category" in data
            assert "score_distribution" in data
            assert "margin_vs_score" in data

            # Check average_score is a number
            assert isinstance(data["average_score"], (int, float))
            assert data["average_score"] > 0

            # Check high quality metrics
            assert isinstance(data["high_quality_count"], int)
            assert isinstance(data["high_quality_percentage"], (int, float))
            assert data["high_quality_count"] >= 0
            assert 0 <= data["high_quality_percentage"] <= 100

            # Check by_level (HIGH, MEDIUM, LOW)
            assert "HIGH" in data["by_level"]
            assert "MEDIUM" in data["by_level"]
            assert "LOW" in data["by_level"]

            # Check by_category
            assert "electronics" in data["by_category"]
            assert "home" in data["by_category"]

            # Check score_distribution is a list of dicts
            assert isinstance(data["score_distribution"], list)
            assert len(data["score_distribution"]) == 10
            for bucket in data["score_distribution"]:
                assert "range" in bucket
                assert "count" in bucket
                assert isinstance(bucket["count"], int)

            # Check margin_vs_score is a list
            assert isinstance(data["margin_vs_score"], list)
            assert len(data["margin_vs_score"]) <= 100  # Limited to 100 points
            if len(data["margin_vs_score"]) > 0:
                point = data["margin_vs_score"][0]
                assert "margin" in point
                assert "score" in point
                assert "category" in point
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_recommendation_stats_with_min_score(db_session):
    """Test getting recommendation statistics with min_score filter."""
    # Override get_db dependency
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        # Create candidates with different scores
        # High quality (score ~77)
        candidate1 = await _create_test_candidate(
            db_session,
            title="High Quality Product",
            priority_score=0.9,
            sales_count=5000,
            rating=Decimal("4.8"),
        )
        await _add_pricing_assessment(
            db_session, candidate1.id, margin_percentage=Decimal("45.0")
        )
        await _add_risk_assessment(db_session, candidate1.id, score=10)
        await _add_supplier_match(db_session, candidate1.id, confidence_score=Decimal("0.95"))

        # Low quality (score ~19.5)
        candidate2 = await _create_test_candidate(
            db_session,
            title="Low Quality Product",
            priority_score=0.2,
            sales_count=50,
            rating=Decimal("3.5"),
        )
        await _add_pricing_assessment(
            db_session,
            candidate2.id,
            margin_percentage=Decimal("15.0"),
        )
        await _add_risk_assessment(db_session, candidate2.id, score=80)
        await _add_supplier_match(db_session, candidate2.id, confidence_score=Decimal("0.3"))

        await db_session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Test with min_score=60 (should filter out low quality)
            response = await client.get("/api/v1/recommendations/stats/overview?min_score=60")
            assert response.status_code == 200

            data = response.json()
            # Should only include high quality candidate
            assert data["total_recommendations"] == 1
            assert data["by_level"]["HIGH"] >= 1
            assert data["by_level"]["LOW"] == 0

            # Test with min_score=0 (should include all)
            response = await client.get("/api/v1/recommendations/stats/overview?min_score=0")
            assert response.status_code == 200

            data = response.json()
            assert data["total_recommendations"] == 2
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_recommendation_stats_empty(db_session):
    """Test getting recommendation statistics with no data."""
    # Override get_db dependency
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        await db_session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/recommendations/stats/overview")
            assert response.status_code == 200

            data = response.json()
            assert data["total_recommendations"] == 0
            assert data["average_score"] == 0.0
            assert data["high_quality_count"] == 0
            assert data["high_quality_percentage"] == 0.0
            assert data["by_level"] == {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
            assert data["by_category"] == {}
            assert len(data["score_distribution"]) == 10
            assert data["margin_vs_score"] == []
    finally:
        app.dependency_overrides.clear()


