"""Feedback aggregator service for closed-loop historical feedback.

Phase 6: Reads historical performance data from DB and provides prior signals
for seed recall and business scoring.

Stage 4 Enhancement: Prioritizes real profit/refund facts, falls back to theoretical signals.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ProfitabilityDecision, RiskDecision
from app.core.logging import get_logger
from app.db.models import CandidateProduct, PlatformListing, PricingAssessment, RiskAssessment, SupplierMatch


class FeedbackAggregator:
    """Lightweight service for reading historical feedback from DB."""

    def __init__(
        self,
        *,
        lookback_days: int = 90,
        prior_cap: float = 5.0,
    ):
        self.lookback_days = lookback_days
        self.prior_cap = prior_cap
        self.logger = get_logger(__name__)
        self._seed_priors: dict[tuple[str, str], float] = {}
        self._shop_priors: dict[str, float] = {}
        self._supplier_priors: dict[tuple[str, str], float] = {}
        self._high_performing_seeds: list[tuple[str, str, float]] = []
        self._high_performing_seeds_by_category: dict = {}

    async def refresh(self, db: AsyncSession) -> None:
        """Refresh historical feedback cache from DB.

        Stage 4 Enhancement: Prioritizes real profit/refund facts when available,
        falls back to theoretical signals (PricingAssessment, RiskAssessment) when insufficient.
        """
        cutoff = datetime.now(UTC) - timedelta(days=self.lookback_days)

        # Import Stage 4 services for real profit/refund data
        from app.services.profit_ledger_service import ProfitLedgerService
        from app.services.refund_analysis_service import RefundAnalysisService

        profit_service = ProfitLedgerService()
        refund_service = RefundAnalysisService()

        sales_subquery = (
            select(
                PlatformListing.candidate_product_id.label("candidate_product_id"),
                func.coalesce(func.sum(PlatformListing.total_sales), 0).label("total_sales"),
            )
            .group_by(PlatformListing.candidate_product_id)
            .subquery()
        )

        stmt = (
            select(
                CandidateProduct.id,
                CandidateProduct.category,
                CandidateProduct.normalized_attributes,
                PricingAssessment.profitability_decision,
                PricingAssessment.margin_percentage,
                RiskAssessment.decision,
                func.coalesce(sales_subquery.c.total_sales, 0).label("total_sales"),
            )
            .outerjoin(PricingAssessment, PricingAssessment.candidate_product_id == CandidateProduct.id)
            .outerjoin(RiskAssessment, RiskAssessment.candidate_product_id == CandidateProduct.id)
            .outerjoin(sales_subquery, sales_subquery.c.candidate_product_id == CandidateProduct.id)
            .where(CandidateProduct.created_at >= cutoff)
        )

        result = await db.execute(stmt)
        rows = result.all()

        seed_stats: dict[tuple[str, str], list[float]] = {}
        seed_categories: dict[tuple[str, str], set[str]] = {}
        shop_stats: dict[str, list[float]] = {}
        supplier_stats: dict[tuple[str, str], list[float]] = {}

        for row in rows:
            attrs = row.normalized_attributes or {}
            category = row.category
            seed_type = attrs.get("seed_type")
            matched_keyword = attrs.get("matched_keyword")
            shop_name = attrs.get("shop_name")
            profitability = row.profitability_decision
            risk = row.decision
            margin = row.margin_percentage or Decimal("0")
            sales = row.total_sales or 0

            # Stage 4 Enhancement: Try to get real profit/refund data
            # Get variant_id from candidate if available
            variant_id = None
            variant_stmt = select(PlatformListing.product_variant_id).where(
                PlatformListing.candidate_product_id == row.id
            )
            variant_result = await db.execute(variant_stmt)
            variant_row = variant_result.first()
            if variant_row and variant_row[0]:
                variant_id = variant_row[0]

            # Try to get real profit snapshot
            real_profit_snapshot = None
            real_refund_rate = None
            if variant_id:
                try:
                    real_profit_snapshot = await profit_service.get_profit_snapshot(
                        db=db,
                        product_variant_id=variant_id,
                        start_date=(datetime.now(UTC) - timedelta(days=self.lookback_days)).date(),
                    )
                    real_refund_rate = await refund_service.get_refund_rate(
                        db=db,
                        product_variant_id=variant_id,
                        start_date=(datetime.now(UTC) - timedelta(days=self.lookback_days)).date(),
                    )
                except Exception as e:
                    self.logger.debug(
                        "failed_to_fetch_real_profit_refund",
                        variant_id=str(variant_id),
                        error=str(e),
                    )

            # Calculate score with real data priority
            score = 0.0

            # Use real profit if available (entry_count >= 10 for statistical significance)
            if real_profit_snapshot and real_profit_snapshot["entry_count"] >= 10:
                # Real profit-based scoring
                real_margin = real_profit_snapshot.get("overall_margin", 0.0) or 0.0
                if real_margin >= 40.0:
                    score += 3.0  # Excellent real profit
                elif real_margin >= 30.0:
                    score += 2.0  # Good real profit
                elif real_margin >= 20.0:
                    score += 1.0  # Acceptable real profit
                else:
                    score += 0.0  # Poor real profit

                # Real refund rate penalty
                if real_refund_rate:
                    refund_rate_pct = real_refund_rate.get("refund_rate", 0.0)
                    if refund_rate_pct < 5.0:
                        score += 1.0  # Low refund rate bonus
                    elif refund_rate_pct > 15.0:
                        score -= 1.0  # High refund rate penalty

                self.logger.debug(
                    "using_real_profit_refund_for_scoring",
                    variant_id=str(variant_id),
                    real_margin=real_margin,
                    refund_rate=real_refund_rate.get("refund_rate", 0.0) if real_refund_rate else 0.0,
                    score=score,
                )
            else:
                # Fallback to theoretical signals (Stage 1-2 logic)
                if profitability == ProfitabilityDecision.PROFITABLE:
                    score += 2.0
                elif profitability == ProfitabilityDecision.MARGINAL:
                    score += 0.5

                if risk == RiskDecision.PASS:
                    score += 1.5
                elif risk == RiskDecision.REVIEW:
                    score += 0.5

                if margin:
                    score += min(float(margin) / 10.0, 1.0)

                if sales > 0:
                    score += min(sales / 100.0, 1.0)

                self.logger.debug(
                    "using_theoretical_signals_for_scoring",
                    candidate_id=str(row.id),
                    profitability=profitability.value if profitability else None,
                    risk=risk.value if risk else None,
                    score=score,
                )

            if seed_type and matched_keyword:
                key = (matched_keyword, seed_type)
                if key not in seed_stats:
                    seed_stats[key] = []
                seed_stats[key].append(score)
                if category:
                    seed_categories.setdefault(key, set()).add(category)

            if shop_name:
                if shop_name not in shop_stats:
                    shop_stats[shop_name] = []
                shop_stats[shop_name].append(score)

        supplier_stmt = (
            select(
                SupplierMatch.supplier_name,
                SupplierMatch.supplier_url,
                PricingAssessment.profitability_decision,
                PricingAssessment.margin_percentage,
                RiskAssessment.decision,
            )
            .join(CandidateProduct, CandidateProduct.id == SupplierMatch.candidate_product_id)
            .outerjoin(PricingAssessment, PricingAssessment.candidate_product_id == CandidateProduct.id)
            .outerjoin(RiskAssessment, RiskAssessment.candidate_product_id == CandidateProduct.id)
            .where(
                and_(
                    CandidateProduct.created_at >= cutoff,
                    SupplierMatch.selected.is_(True),
                )
            )
        )

        supplier_result = await db.execute(supplier_stmt)
        supplier_rows = supplier_result.all()

        for row in supplier_rows:
            supplier_name = row.supplier_name or ""
            supplier_url = row.supplier_url or ""
            profitability = row.profitability_decision
            risk = row.decision
            margin = row.margin_percentage or Decimal("0")

            score = 0.0
            if profitability == ProfitabilityDecision.PROFITABLE:
                score += 2.0
            elif profitability == ProfitabilityDecision.MARGINAL:
                score += 0.5

            if risk == RiskDecision.PASS:
                score += 1.5
            elif risk == RiskDecision.REVIEW:
                score += 0.5

            if margin:
                score += min(float(margin) / 10.0, 1.0)

            key = (supplier_name, supplier_url)
            if key not in supplier_stats:
                supplier_stats[key] = []
            supplier_stats[key].append(score)

        self._seed_priors = {
            key: min(sum(scores) / len(scores), self.prior_cap) for key, scores in seed_stats.items() if scores
        }
        self._shop_priors = {
            key: min(sum(scores) / len(scores), self.prior_cap) for key, scores in shop_stats.items() if scores
        }
        self._supplier_priors = {
            key: min(sum(scores) / len(scores), self.prior_cap) for key, scores in supplier_stats.items() if scores
        }

        self._high_performing_seeds = [
            (seed, seed_type, prior) for (seed, seed_type), prior in self._seed_priors.items() if prior >= 2.0
        ]
        self._high_performing_seeds.sort(key=lambda x: x[2], reverse=True)

        seeds_by_category: dict[str, list[tuple[str, str, float]]] = {}
        for seed, seed_type, prior in self._high_performing_seeds:
            for category_name in seed_categories.get((seed, seed_type), set()):
                seeds_by_category.setdefault(category_name, []).append((seed, seed_type, prior))
        for category_name, items in seeds_by_category.items():
            items.sort(key=lambda x: x[2], reverse=True)
        self._high_performing_seeds_by_category = seeds_by_category

        self.logger.info(
            "feedback_aggregator_refreshed",
            seed_priors=len(self._seed_priors),
            shop_priors=len(self._shop_priors),
            supplier_priors=len(self._supplier_priors),
            high_performing_seeds=len(self._high_performing_seeds),
        )

    def get_high_performing_seeds(self, category: str | None, limit: int) -> list[str]:
        """Return high-performing seeds, optionally filtered by category."""
        if category:
            items = self._high_performing_seeds_by_category.get(category, [])
            return [seed for seed, _seed_type, _prior in items[:limit]]
        return [seed for seed, _seed_type, _prior in self._high_performing_seeds[:limit]]

    def get_seed_performance_prior(self, seed: str, seed_type: str) -> float:
        """Return historical performance prior for a seed."""
        return self._seed_priors.get((seed, seed_type), 0.0)

    def get_shop_performance_prior(self, shop_name: str) -> float:
        """Return historical performance prior for a shop."""
        return self._shop_priors.get(shop_name, 0.0)

    def get_supplier_performance_prior(self, supplier_name: str, supplier_url: str) -> float:
        """Return historical performance prior for a supplier."""
        return self._supplier_priors.get((supplier_name, supplier_url), 0.0)
