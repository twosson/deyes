"""Keyword legitimizer service for opportunity-first product selection.

Converts seeds into valid keywords using AlphaShop keyword.search API.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

from app.clients.alphashop import AlphaShopClient
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.seed_pool_builder import Seed

logger = get_logger(__name__)


@dataclass
class ValidKeyword:
    """A validated keyword ready for newproduct.report."""

    seed: Seed
    matched_keyword: str
    match_type: str  # "exact" / "normalized" / "related" / "fallback"
    opp_score: Optional[float]
    search_volume: Optional[int]
    competition_density: str  # "low" / "medium" / "high"
    is_valid_for_report: bool
    raw: dict[str, Any]
    report_keyword: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "seed": self.seed.to_dict(),
            "matched_keyword": self.matched_keyword,
            "match_type": self.match_type,
            "opp_score": self.opp_score,
            "search_volume": self.search_volume,
            "competition_density": self.competition_density,
            "is_valid_for_report": self.is_valid_for_report,
            "raw": self.raw,
            "report_keyword": self.report_keyword,
        }


class KeywordLegitimizerService:
    """Legitimize seeds into valid keywords using AlphaShop keyword.search."""

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

    async def legitimize_seeds(
        self,
        *,
        seeds: list[Seed],
        region: str,
        platform: str,
        min_opp_score: float = 20.0,
    ) -> list[ValidKeyword]:
        """Legitimize seeds into valid keywords."""
        client = await self._get_alphashop_client()
        if client is None:
            self.logger.warning(
                "keyword_legitimizer_unavailable",
                reason="missing_configuration_or_disabled",
            )
            return []

        valid_keywords: list[ValidKeyword] = []
        api_call_count = 0
        api_error_count = 0
        min_interval_ms = max(self.settings.alphashop_keyword_search_min_interval_ms, 0)

        for index, seed in enumerate(seeds):
            if index > 0 and min_interval_ms > 0:
                await asyncio.sleep(min_interval_ms / 1000)
            api_call_count += 1
            try:
                response = await client.search_keywords(
                    platform=platform,
                    region=region,
                    keyword=seed.term,
                    listing_time=self.settings.keyword_generation_listing_time,
                )

                keyword_list = response.get("keyword_list") or []
                if not keyword_list:
                    self.logger.debug(
                        "seed_legitimization_no_results",
                        seed=seed.term,
                        region=region,
                    )
                    continue

                # Find best match
                best_match = self._select_best_match(seed.term, keyword_list)
                if not best_match:
                    continue

                # Extract metrics
                opp_score = self._extract_opp_score(best_match)
                search_volume = self._extract_search_volume(best_match)
                competition_density = self._extract_competition_density(best_match)
                matched_keyword = self._extract_keyword_text(best_match)
                report_keyword = self._extract_report_keyword(best_match)

                # Determine match type
                match_type = self._determine_match_type(seed.term, matched_keyword)

                # Check if valid for report
                is_valid = (
                    opp_score is not None
                    and opp_score >= min_opp_score
                    and matched_keyword
                    and report_keyword
                    and not self._is_too_generic(matched_keyword)
                )

                valid_keywords.append(
                    ValidKeyword(
                        seed=seed,
                        matched_keyword=matched_keyword,
                        match_type=match_type,
                        opp_score=opp_score,
                        search_volume=search_volume,
                        competition_density=competition_density,
                        is_valid_for_report=is_valid,
                        raw=best_match,
                        report_keyword=report_keyword,
                    )
                )

            except Exception as exc:
                api_error_count += 1
                self.logger.warning(
                    "seed_legitimization_failed",
                    seed=seed.term,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                continue

        report_safe_count = len([kw for kw in valid_keywords if kw.is_valid_for_report])
        invalid_count = len([kw for kw in valid_keywords if not kw.is_valid_for_report])

        match_type_breakdown = {}
        for kw in valid_keywords:
            match_type_breakdown[kw.match_type] = match_type_breakdown.get(kw.match_type, 0) + 1

        avg_opp_score = None
        opp_scores = [kw.opp_score for kw in valid_keywords if kw.opp_score is not None]
        if opp_scores:
            avg_opp_score = sum(opp_scores) / len(opp_scores)

        self.logger.info(
            "seed_legitimization_completed",
            total_seeds=len(seeds),
            valid_keywords=report_safe_count,
            invalid_keywords=invalid_count,
            legitimization_success_rate=round(report_safe_count / len(seeds), 3) if seeds else 0.0,
            match_type_breakdown=match_type_breakdown,
            avg_opp_score=round(avg_opp_score, 2) if avg_opp_score else None,
            exact_matches=match_type_breakdown.get("exact", 0),
            normalized_matches=match_type_breakdown.get("normalized", 0),
            related_matches=match_type_breakdown.get("related", 0),
            fallback_matches=match_type_breakdown.get("fallback", 0),
            api_call_count=api_call_count,
            api_error_count=api_error_count,
            api_error_rate=round(api_error_count / api_call_count, 3) if api_call_count else 0.0,
        )

        return valid_keywords

    def _select_best_match(self, seed: str, keyword_list: list[dict]) -> Optional[dict]:
        """Select best keyword match for seed."""
        seed_lower = seed.lower().strip()

        # Try exact match first
        for item in keyword_list:
            keyword = self._extract_keyword_text(item)
            if keyword and keyword.lower().strip() == seed_lower:
                return item

        # Try normalized match (singular/plural)
        seed_normalized = self._normalize_keyword(seed_lower)
        for item in keyword_list:
            keyword = self._extract_keyword_text(item)
            if keyword and self._normalize_keyword(keyword.lower().strip()) == seed_normalized:
                return item

        # Try substring match
        for item in keyword_list:
            keyword = self._extract_keyword_text(item)
            if keyword:
                keyword_lower = keyword.lower().strip()
                if seed_lower in keyword_lower or keyword_lower in seed_lower:
                    return item

        # Fallback to first result
        return keyword_list[0] if keyword_list else None

    def _normalize_keyword(self, keyword: str) -> str:
        """Normalize keyword for matching (remove plural, etc.)."""
        if keyword.endswith("es"):
            return keyword[:-2]
        if keyword.endswith("s"):
            return keyword[:-1]
        return keyword

    def _determine_match_type(self, seed: str, matched_keyword: str) -> str:
        """Determine match type between seed and matched keyword."""
        seed_lower = seed.lower().strip()
        matched_lower = matched_keyword.lower().strip()

        if seed_lower == matched_lower:
            return "exact"

        if self._normalize_keyword(seed_lower) == self._normalize_keyword(matched_lower):
            return "normalized"

        if seed_lower in matched_lower or matched_lower in seed_lower:
            return "related"

        return "fallback"

    def _is_too_generic(self, keyword: str) -> bool:
        """Check if keyword is too generic, contains brand terms, or has invalid format for newproduct.report."""
        import re

        generic_patterns = [
            "electronics",
            "fashion",
            "home",
            "beauty",
            "sports",
            "toys",
            "jewelry",
            "wireless electronics",
            "home electronics",
        ]
        brand_keywords = [
            "iphone",
            "ipad",
            "samsung",
            "nike",
            "adidas",
            "apple",
            "sony",
            "lg",
            "dell",
            "hp",
            # E-reader brands
            "bigme",
            "boox",
            "onyx",
            "kindle",
            "kobo",
            "pocketbook",
            "remarkable",
            # Other common brands
            "xiaomi",
            "huawei",
            "lenovo",
            "asus",
            "acer",
            "microsoft",
            "google",
            "fitbit",
            "garmin",
            "gopro",
        ]
        keyword_lower = keyword.lower().strip()
        if keyword_lower in generic_patterns:
            return True
        # Check if keyword contains any brand term
        for brand in brand_keywords:
            if brand in keyword_lower:
                return True
        # Filter age ranges and year ranges like "8-12", "3-5 years"
        if re.search(r"\b\d+\s*-\s*\d+\b", keyword_lower):
            return True
        if re.search(r"\b\d+\s*(year|years|yr|yrs|age|ages)\b", keyword_lower):
            return True
        # Filter non-ASCII keywords to avoid unsupported locale issues
        if any(ord(char) > 127 for char in keyword):
            return True
        # Filter keywords with too many special characters
        if re.search(r"[^a-z0-9\s\-]", keyword_lower):
            return True
        return False

    def _extract_keyword_text(self, item: dict) -> str:
        """Extract keyword text from AlphaShop result."""
        for key in ("keyword", "query", "searchKeyword", "keywordName", "term", "title"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        radar = item.get("radar")
        if isinstance(radar, dict):
            for key in ("keyword", "query", "searchKeyword"):
                value = radar.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        return ""

    def _extract_report_keyword(self, item: dict) -> Optional[str]:
        """Extract strict report-safe keyword from AlphaShop result.

        AlphaShop newproduct.report requires productKeyword to be one of the
        exact keywords returned in keyword.search's `keyword` field.
        """
        value = item.get("keyword")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _extract_opp_score(self, item: dict) -> Optional[float]:
        """Extract opportunity score from AlphaShop result."""
        opp_score = item.get("oppScore")
        if opp_score is not None:
            try:
                return float(opp_score)
            except (ValueError, TypeError):
                pass
        return None

    def _extract_search_volume(self, item: dict) -> Optional[int]:
        """Extract search volume from AlphaShop result."""
        direct_volume = item.get("searchVolume")
        if direct_volume is not None:
            try:
                return max(int(direct_volume), 100)
            except (ValueError, TypeError):
                pass

        sales_info = item.get("salesInfo")
        if isinstance(sales_info, dict):
            sales_volume = sales_info.get("searchVolume")
            if sales_volume is not None:
                try:
                    return max(int(sales_volume), 100)
                except (ValueError, TypeError):
                    pass

        return None

    def _extract_competition_density(self, item: dict) -> str:
        """Extract competition density from AlphaShop result.

        Competition density is derived from opportunity score:
        - opp_score >= 70: LOW competition (strong opportunity)
        - opp_score >= 40: MEDIUM competition (moderate opportunity)
        - opp_score >= 20: MEDIUM competition (acceptable opportunity, not high)
        - opp_score < 20: HIGH competition (weak opportunity)

        This aligns with min_opp_score filter which defaults to 20.0.
        """
        opp_score = self._extract_opp_score(item)
        if opp_score is not None:
            if opp_score >= 70:
                return "low"
            if opp_score >= 20:
                return "medium"
            return "high"

        # Fallback to heuristic
        keyword = self._extract_keyword_text(item)
        word_count = len(keyword.split()) if keyword else 0
        if word_count <= 2:
            return "high"
        if word_count <= 4:
            return "medium"
        return "low"
