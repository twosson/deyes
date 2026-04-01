"""Opportunity discovery service for opportunity-first product selection.

Uses AlphaShop newproduct.report API to discover market opportunities from valid keywords.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.clients.alphashop import AlphaShopClient
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.keyword_legitimizer import ValidKeyword

logger = get_logger(__name__)


@dataclass
class OpportunityDraft:
    """A discovered market opportunity draft."""

    keyword: str
    title: str
    opportunity_score: Optional[float]
    product_list: list[dict[str, Any]]
    keyword_summary: dict[str, Any]
    evidence: dict[str, Any]
    raw: dict[str, Any]

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "keyword": self.keyword,
            "title": self.title,
            "opportunity_score": self.opportunity_score,
            "product_list": self.product_list,
            "keyword_summary": self.keyword_summary,
            "evidence": self.evidence,
            "raw": self.raw,
        }


class OpportunityDiscoveryService:
    """Discover opportunities using AlphaShop newproduct.report API."""

    def __init__(
        self,
        alphashop_client: Optional[AlphaShopClient] = None,
    ):
        self.settings = get_settings().model_copy(deep=True)
        self._alphashop_client = alphashop_client
        self._created_client = False
        self.logger = logger

    async def _get_alphashop_client(self) -> AlphaShopClient | None:
        """Get or create AlphaShop client."""
        if self._alphashop_client is not None:
            return self._alphashop_client
        if not self.settings.alphashop_enabled:
            return None
        if not self.settings.alphashop_api_key or not self.settings.alphashop_secret_key:
            return None
        self._alphashop_client = AlphaShopClient()
        self._created_client = True
        return self._alphashop_client

    async def close(self) -> None:
        """Close underlying AlphaShop client."""
        if self._created_client and self._alphashop_client is not None:
            await self._alphashop_client.close()
            self._alphashop_client = None
            self._created_client = False

    async def discover_opportunities(
        self,
        *,
        valid_keywords: list[ValidKeyword],
        region: str,
        platform: str,
        max_reports: int = 5,
        report_size: int = 10,
    ) -> list[OpportunityDraft]:
        """Discover opportunities from valid keywords using newproduct.report."""
        client = await self._get_alphashop_client()
        if client is None:
            self.logger.warning(
                "opportunity_discovery_unavailable",
                reason="missing_configuration_or_disabled",
            )
            return []

        opportunities: list[OpportunityDraft] = []

        # Sort by opportunity score descending, then limit
        report_keywords = [kw for kw in valid_keywords if kw.is_valid_for_report]
        report_keywords.sort(key=lambda kw: kw.opp_score or 0.0, reverse=True)
        report_keywords = report_keywords[:max_reports]

        for valid_kw in report_keywords:
            try:
                report_keyword = valid_kw.report_keyword
                if not report_keyword:
                    self.logger.info(
                        "opportunity_report_skipped_missing_report_keyword",
                        keyword=valid_kw.matched_keyword,
                        match_type=valid_kw.match_type,
                    )
                    continue

                # Try with listing_time first
                try:
                    response = await client.newproduct_report(
                        platform=platform,
                        region=region,
                        product_keyword=report_keyword,
                        listing_time=self.settings.keyword_generation_listing_time,
                        size=report_size,
                    )
                except RuntimeError as exc:
                    # If AlphaShop rejects with FAIL_REQUEST_PARAMETER_ILLEGAL, retry with minimal payload
                    error_code = getattr(exc, "alphashop_code", None)
                    if error_code == "FAIL_REQUEST_PARAMETER_ILLEGAL":
                        self.logger.info(
                            "opportunity_report_retry_minimal_payload",
                            keyword=valid_kw.matched_keyword,
                            report_keyword=report_keyword,
                            original_error=str(exc),
                        )
                        response = await client.newproduct_report(
                            platform=platform,
                            region=region,
                            product_keyword=report_keyword,
                            listing_time=None,
                            size=None,
                        )
                    else:
                        raise

                product_list = response.get("product_list") or []
                keyword_summary = response.get("keyword_summary") or {}

                if not product_list:
                    self.logger.info(
                        "opportunity_report_empty",
                        keyword=valid_kw.matched_keyword,
                        region=region,
                        opp_score=valid_kw.opp_score,
                    )
                    continue

                # Create opportunity draft
                title = self._generate_opportunity_title(valid_kw.matched_keyword, keyword_summary)
                opportunity_score = self._extract_opportunity_score(keyword_summary, valid_kw)
                evidence = {
                    "seed": valid_kw.seed.to_dict(),
                    "valid_keyword": valid_kw.to_dict(),
                    "report_keyword": report_keyword,
                    "keyword_summary": keyword_summary,
                    "product_count": len(product_list),
                }

                opportunities.append(
                    OpportunityDraft(
                        keyword=valid_kw.matched_keyword,
                        title=title,
                        opportunity_score=opportunity_score,
                        product_list=product_list,
                        keyword_summary=keyword_summary,
                        evidence=evidence,
                        raw=response,
                    )
                )

            except Exception as exc:
                self.logger.warning(
                    "opportunity_discovery_failed",
                    keyword=valid_kw.matched_keyword,
                    opp_score=valid_kw.opp_score,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                continue

        # Sort opportunities by score descending
        opportunities.sort(key=lambda opp: opp.opportunity_score or 0.0, reverse=True)

        avg_opportunity_score = None
        if opportunities:
            scores = [opp.opportunity_score for opp in opportunities if opp.opportunity_score is not None]
            if scores:
                avg_opportunity_score = sum(scores) / len(scores)

        total_products = sum(len(opp.product_list) for opp in opportunities)
        avg_products_per_opportunity = total_products / len(opportunities) if opportunities else 0

        self.logger.info(
            "opportunity_discovery_completed",
            total_valid_keywords=len(report_keywords),
            opportunities_found=len(opportunities),
            discovery_success_rate=round(len(opportunities) / len(report_keywords), 3) if report_keywords else 0.0,
            avg_opportunity_score=round(avg_opportunity_score, 2) if avg_opportunity_score else None,
            total_products_discovered=total_products,
            avg_products_per_opportunity=round(avg_products_per_opportunity, 1),
            top_opportunity_score=round(opportunities[0].opportunity_score, 2) if opportunities and opportunities[0].opportunity_score else None,
        )

        return opportunities

    def _generate_opportunity_title(self, keyword: str, keyword_summary: dict) -> str:
        """Generate opportunity title from keyword and summary."""
        if keyword_summary.get("summary"):
            return keyword_summary["summary"]
        return f"New product opportunity: {keyword}"

    def _extract_opportunity_score(self, keyword_summary: dict, valid_kw: ValidKeyword) -> Optional[float]:
        """Extract opportunity score from keyword summary or fallback to valid keyword score."""
        for key in ("opportunityScore", "oppScore", "score"):
            value = keyword_summary.get(key)
            if value is not None:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    pass

        return valid_kw.opp_score
