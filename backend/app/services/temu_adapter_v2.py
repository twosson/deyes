"""Temu source adapter using browser pool for production scraping."""
from __future__ import annotations

import asyncio
import hashlib
import random
import re
import time
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import urlencode, urljoin

if TYPE_CHECKING:
    from playwright.async_api import Page

from app.core.config import get_settings
from app.core.enums import SourcePlatform
from app.core.logging import get_logger
from app.services.browser_pool import BrowserPool
from app.services.browsing import BrowsingRequest, BrowsingService
from app.services.source_adapter import ProductData, SourceAdapter

logger = get_logger(__name__)


class TemuSourceAdapterV2(SourceAdapter):
    """Temu product scraper using the browsing service with anti-detection."""

    PRODUCT_CARD_WAIT_TIMEOUT_MS = 5000
    MAX_SCROLL_ATTEMPTS = 3

    def __init__(
        self,
        browser_pool: Optional[BrowserPool] = None,
        browsing_service: Optional[BrowsingService] = None,
    ):
        self.settings = get_settings()
        self.logger = get_logger(__name__)
        self._browser_pool = browser_pool
        self._browsing_service = browsing_service

    async def _get_browsing_service(self) -> BrowsingService:
        """Get or create the browsing service instance."""
        if self._browsing_service is None:
            self._browsing_service = BrowsingService(browser_pool=self._browser_pool)
        return self._browsing_service

    async def fetch_products(
        self,
        category: Optional[str] = None,
        keywords: Optional[list[str]] = None,
        price_min: Optional[Decimal] = None,
        price_max: Optional[Decimal] = None,
        limit: int = 10,
        region: Optional[str] = None,
    ) -> list[ProductData]:
        """Fetch products from Temu search results using the browsing service."""
        search_url = self._build_search_url(category=category, keywords=keywords)
        last_error: Optional[Exception] = None

        self.logger.info(
            "temu_fetch_started",
            category=category,
            region=region,
            keywords=keywords or [],
            price_min=str(price_min) if price_min is not None else None,
            price_max=str(price_max) if price_max is not None else None,
            limit=limit,
            search_url=search_url,
        )

        request = BrowsingRequest(
            target="temu",
            workflow="product_discovery",
            region=region,
            network_mode="sticky",
            session_scope="request",
            tags={"adapter": "temu_v2"},
        )

        for attempt in range(1, self.settings.scraper_max_retries + 1):
            started_at = time.perf_counter()
            browsing_service: Optional[BrowsingService] = None

            try:
                browsing_service = await self._get_browsing_service()

                async with browsing_service.get_page(request) as page:
                    await page.goto(
                        search_url,
                        wait_until="domcontentloaded",
                        timeout=self.settings.scraper_timeout,
                    )
                    await self._apply_human_delay()
                    await self._wait_for_search_results(page)

                    if self.settings.environment == "development":
                        page_html = await page.content()
                        self.logger.info(
                            "temu_page_snapshot",
                            url=page.url,
                            html_length=len(page_html),
                            html_preview=page_html[:2000],
                        )

                    product_payloads = await self._collect_product_payloads(page=page, limit=limit)

                    self.logger.info(
                        "temu_payloads_collected",
                        payload_count=len(product_payloads),
                        sample_payload=product_payloads[0] if product_payloads else None,
                    )

                    products = self._parse_product_payloads(
                        payloads=product_payloads,
                        category=category,
                        keywords=keywords,
                        price_min=price_min,
                        price_max=price_max,
                        limit=limit,
                    )

                duration_ms = int((time.perf_counter() - started_at) * 1000)
                self.logger.info(
                    "temu_fetch_completed",
                    count=len(products),
                    duration_ms=duration_ms,
                    attempt=attempt,
                )
                return products

            except Exception as exc:
                last_error = exc
                duration_ms = int((time.perf_counter() - started_at) * 1000)
                pool_stats = browsing_service.get_stats() if browsing_service is not None else None
                self.logger.warning(
                    "temu_fetch_attempt_failed",
                    attempt=attempt,
                    duration_ms=duration_ms,
                    error=str(exc),
                    pool_stats=pool_stats,
                )
                if attempt < self.settings.scraper_max_retries:
                    await asyncio.sleep(2 ** (attempt - 1))

        self.logger.error(
            "temu_fetch_failed",
            error=str(last_error) if last_error else "unknown error",
            category=category,
            region=region,
            keywords=keywords or [],
        )
        return []

    async def _apply_human_delay(self) -> None:
        """Apply randomized human-like delay."""
        # More varied delays
        delay_type = random.random()
        if delay_type < 0.6:
            # Quick action
            await asyncio.sleep(random.uniform(0.8, 1.5))
        elif delay_type < 0.9:
            # Normal action
            await asyncio.sleep(random.uniform(1.5, 3.0))
        else:
            # Slow/distracted action
            await asyncio.sleep(random.uniform(3.0, 5.0))

    def _build_search_url(
        self,
        category: Optional[str] = None,
        keywords: Optional[list[str]] = None,
    ) -> str:
        """Build a Temu search URL from category and keywords."""
        search_terms = [term.strip() for term in (keywords or []) if term and term.strip()]
        if category and category.strip():
            search_terms.append(category.strip())

        query = " ".join(search_terms).strip() or "hot sale"
        return f"{self.settings.temu_base_url}/search_result.html?{urlencode({'search_key': query})}"

    async def _wait_for_search_results(self, page: Page) -> None:
        """Wait until the page appears to contain product results."""
        try:
            await page.wait_for_function(
                r"""
                () => {
                    const cards = Array.from(document.querySelectorAll('a[href], [role="link"], article, li, section, div'));
                    return cards.some((node) => {
                        const text = (node.innerText || node.textContent || '').trim();
                        const hasImage = !!node.querySelector('img');
                        const hasPrice = /(?:\$|usd|\d+[\.,]\d{1,2})/i.test(text);
                        return hasImage && hasPrice && text.length > 10;
                    });
                }
                """,
                timeout=min(self.settings.scraper_timeout, self.PRODUCT_CARD_WAIT_TIMEOUT_MS),
            )
            return
        except Exception:
            pass

        page_text = (await page.locator("body").inner_text()).lower()
        if any(token in page_text for token in ["captcha", "verify you are human", "unusual traffic"]):
            raise RuntimeError("Temu presented anti-bot verification")

        if not page_text.strip():
            raise TimeoutError("Temu search page did not load content")

    async def _collect_product_payloads(self, page: Page, limit: int) -> list[dict[str, Any]]:
        """Collect raw product payloads from the current search page."""
        payloads: list[dict[str, Any]] = []

        for _ in range(self.MAX_SCROLL_ATTEMPTS):
            payloads = await page.evaluate(
                r"""
                (maxItems) => {
                    const pickTexts = (root, selectors, matcher = null) => {
                        const values = [];
                        for (const selector of selectors) {
                            for (const node of root.querySelectorAll(selector)) {
                                const text = (node.textContent || node.innerText || '').trim();
                                if (!text) continue;
                                if (matcher && !matcher.test(text)) continue;
                                if (!values.includes(text)) values.push(text);
                            }
                        }
                        return values;
                    };

                    const anchors = Array.from(document.querySelectorAll('a[href]'));
                    const records = [];
                    const seen = new Set();

                    for (const anchor of anchors) {
                        let href = anchor.getAttribute('href') || '';
                        if (!href || href.startsWith('javascript:') || href.startsWith('#') || seen.has(href)) continue;

                        const card = anchor.closest('[data-testid*="product"], [class*="product"], [class*="goods"], [class*="item"], article, li, section') || anchor;
                        const cardText = (card.innerText || card.textContent || '').trim();
                        const image = card.querySelector('img');

                        const hasImage = !!image;
                        const hasPrice = /(?:\$|usd|\d+[\.,]\d{1,2})/i.test(cardText);
                        const hasEnoughText = cardText.length > 10;

                        if (!hasImage || !hasPrice || !hasEnoughText) continue;

                        const titleText = (anchor.getAttribute('title') || anchor.getAttribute('aria-label') || '').trim();

                        seen.add(href);
                        records.push({
                            href,
                            title: titleText,
                            text: cardText,
                            image_url: image?.src || image?.getAttribute('data-src') || image?.getAttribute('srcset')?.split(' ')[0] || null,
                            image_alt: image?.alt || null,
                            html: (card.outerHTML || '').substring(0, 5000),
                            title_candidates: pickTexts(card, ['[data-testid*="title"]', '[class*="title"]', '[class*="name"]', 'h1', 'h2', 'h3', 'h4', 'span', 'p']),
                            price_candidates: pickTexts(
                                card,
                                ['[data-testid*="price"]', '[class*="price"]', '[aria-label*="price"]', 'span', 'div', 'p'],
                                /(?:\$|usd|\d+[\.,]\d{1,2})/i,
                            ),
                            sales_candidates: pickTexts(card, ['span', 'div', 'p'], /(?:sold|sales|orders|k sold|\+ sold)/i),
                            rating_candidates: pickTexts(card, ['[data-testid*="rating"]', '[class*="rating"]', '[aria-label*="rating"]', 'span', 'div'], /(?:^|\s)[0-5](?:\.\d)?(?:\s|$|\/5)/),
                            seller_candidates: pickTexts(card, ['[data-testid*="seller"]', '[class*="seller"]', '[class*="shop"]', '[class*="store"]']),
                            category_candidates: pickTexts(card, ['[data-testid*="category"]', '[class*="category"]']),
                        });

                        if (records.length >= maxItems * 4) break;
                    }

                    return records;
                }
                """,
                max(limit, 1),
            )

            if len(payloads) >= limit:
                break

            # Human-like scrolling
            scroll_distance = random.randint(2000, 4000)
            await page.mouse.wheel(0, scroll_distance)
            await self._apply_human_delay()

        return payloads

    def _parse_product_payloads(
        self,
        payloads: list[dict[str, Any]],
        category: Optional[str],
        keywords: Optional[list[str]],
        price_min: Optional[Decimal],
        price_max: Optional[Decimal],
        limit: int,
    ) -> list[ProductData]:
        """Convert raw payloads into ProductData objects."""
        products: list[ProductData] = []

        for payload in payloads:
            try:
                product = self._parse_product_payload(payload)
            except Exception as exc:
                self.logger.warning(
                    "temu_product_parse_failed",
                    source_url=payload.get("href"),
                    error=str(exc),
                )
                continue

            if product is None:
                continue
            if not self._matches_filters(product, category, keywords, price_min, price_max):
                continue

            products.append(product)
            if len(products) >= limit:
                break

        return products

    def _parse_product_payload(self, payload: dict[str, Any]) -> Optional[ProductData]:
        """Parse a single scraped payload into ProductData."""
        source_url = self._normalize_url(payload.get("href"))
        if not source_url:
            return None

        title = self._extract_title(payload)
        if not title:
            return None

        platform_price = self._extract_price(payload)
        if platform_price is None:
            return None

        category = self._first_non_empty(payload.get("category_candidates"))
        seller_info = self._first_non_empty(payload.get("seller_candidates"))
        image_url = self._normalize_url(payload.get("image_url"))
        rating = self._extract_rating(payload)
        sales_count = self._extract_sales_count(payload)
        source_product_id = self._extract_product_id(source_url=source_url, title=title)

        return ProductData(
            source_platform=SourcePlatform.TEMU,
            source_product_id=source_product_id,
            source_url=source_url,
            title=title,
            category=category,
            currency="USD",
            platform_price=platform_price,
            sales_count=sales_count,
            rating=rating,
            main_image_url=image_url,
            raw_payload={
                "search_text": payload.get("text"),
                "title_candidates": payload.get("title_candidates", []),
                "price_candidates": payload.get("price_candidates", []),
                "sales_candidates": payload.get("sales_candidates", []),
                "rating_candidates": payload.get("rating_candidates", []),
                "seller_candidates": payload.get("seller_candidates", []),
                "seller_info": seller_info,
                "image_alt": payload.get("image_alt"),
                "card_html": (payload.get("html") or "")[:4000],
            },
        )

    def _extract_title(self, payload: dict[str, Any]) -> Optional[str]:
        """Extract product title from scraped payload."""
        candidates = [payload.get("title"), payload.get("image_alt")]
        candidates.extend(payload.get("title_candidates", []))
        candidates.extend(self._text_lines(payload.get("text")))

        for candidate in candidates:
            text = self._clean_text(candidate)
            if not text:
                continue
            if self._looks_like_price(text) or self._looks_like_sales(text) or self._looks_like_rating(text):
                continue
            if len(text) < 6:
                continue
            return text

        return None

    def _extract_price(self, payload: dict[str, Any]) -> Optional[Decimal]:
        """Extract product price from scraped payload."""
        candidates = list(payload.get("price_candidates", []))
        candidates.extend(self._text_lines(payload.get("text")))

        for candidate in candidates:
            price = self._parse_decimal(candidate)
            if price is not None and price > 0:
                return price

        return None

    def _extract_sales_count(self, payload: dict[str, Any]) -> Optional[int]:
        """Extract sales count from scraped payload."""
        candidates = list(payload.get("sales_candidates", []))
        candidates.extend(self._text_lines(payload.get("text")))

        for candidate in candidates:
            sales_count = self._parse_sales_count(candidate)
            if sales_count is not None:
                return sales_count

        return None

    def _extract_rating(self, payload: dict[str, Any]) -> Optional[Decimal]:
        """Extract product rating from scraped payload."""
        candidates = list(payload.get("rating_candidates", []))
        candidates.extend(self._text_lines(payload.get("text")))

        for candidate in candidates:
            rating = self._parse_rating(candidate)
            if rating is not None:
                return rating

        return None

    def _matches_filters(
        self,
        product: ProductData,
        category: Optional[str],
        keywords: Optional[list[str]],
        price_min: Optional[Decimal],
        price_max: Optional[Decimal],
    ) -> bool:
        """Apply category, keyword, and price filters after scraping."""
        if category:
            haystacks = [product.category or "", product.title]
            if not any(category.lower() in haystack.lower() for haystack in haystacks):
                return False

        if keywords:
            title_lower = product.title.lower()
            normalized_keywords = [keyword.lower() for keyword in keywords if keyword]
            if normalized_keywords and not any(keyword in title_lower for keyword in normalized_keywords):
                return False

        if price_min is not None and product.platform_price is not None:
            if product.platform_price < price_min:
                return False
        if price_max is not None and product.platform_price is not None:
            if product.platform_price > price_max:
                return False

        return True

    def _extract_product_id(self, source_url: str, title: str) -> str:
        """Extract a stable product identifier from Temu product URLs."""
        patterns = [
            r"goods_id=(\d+)",
            r"-g-(\d+)\.html",
            r"/g-(\d+)\.html",
            r"sku=(\d+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, source_url)
            if match:
                return match.group(1)

        digest = hashlib.sha1(f"{source_url}:{title}".encode("utf-8")).hexdigest()
        return digest[:16]

    def _normalize_url(self, raw_url: Optional[str]) -> Optional[str]:
        """Convert relative Temu URLs into absolute URLs."""
        if not raw_url:
            return None
        normalized = raw_url.strip()
        if normalized.startswith("//"):
            return f"https:{normalized}"
        return urljoin(f"{self.settings.temu_base_url}/", normalized)

    def _parse_decimal(self, raw_value: Optional[str]) -> Optional[Decimal]:
        """Parse a price-like string into Decimal."""
        if not raw_value:
            return None

        cleaned = raw_value.lower().replace(",", "").strip()
        if any(token in cleaned for token in ["sold", "sales", "orders", "rating"]):
            return None

        currency_match = re.search(r"(?:\$|usd\s*)(\d+(?:\.\d{1,2})?)", cleaned)
        if currency_match:
            try:
                return Decimal(currency_match.group(1))
            except InvalidOperation:
                return None

        plain_match = re.fullmatch(r"(?:price[:\s]*)?(\d+(?:\.\d{1,2})?)", cleaned)
        if not plain_match:
            return None

        try:
            return Decimal(plain_match.group(1))
        except InvalidOperation:
            return None

    def _parse_sales_count(self, raw_value: Optional[str]) -> Optional[int]:
        """Parse sales text such as '2.5k sold' into an integer."""
        if not raw_value:
            return None

        lowered = raw_value.lower().replace(",", "")
        if not any(token in lowered for token in ["sold", "sales", "orders"]):
            return None

        match = re.search(r"(\d+(?:\.\d+)?)\s*([km])?\s*(?:\+)?", lowered)
        if not match:
            return None

        value = Decimal(match.group(1))
        unit = match.group(2)
        multiplier = Decimal("1")
        if unit == "k":
            multiplier = Decimal("1000")
        elif unit == "m":
            multiplier = Decimal("1000000")

        return int(value * multiplier)

    def _parse_rating(self, raw_value: Optional[str]) -> Optional[Decimal]:
        """Parse rating text like '4.8/5' or 'Rated 4.6'."""
        if not raw_value:
            return None

        match = re.search(r"(?<![\d.])([0-5](?:\.\d)?)(?![\d.])(?:\s*/\s*5)?", raw_value)
        if not match:
            return None

        try:
            rating = Decimal(match.group(1))
        except InvalidOperation:
            return None

        if Decimal("0") <= rating <= Decimal("5"):
            return rating
        return None

    def _text_lines(self, raw_text: Optional[str]) -> list[str]:
        """Split a text block into cleaned non-empty lines."""
        if not raw_text:
            return []

        return [self._clean_text(line) for line in raw_text.splitlines() if self._clean_text(line)]

    def _clean_text(self, value: Optional[str]) -> str:
        """Normalize whitespace for scraped text values."""
        if not value:
            return ""
        return re.sub(r"\s+", " ", value).strip()

    def _first_non_empty(self, values: Optional[list[str]]) -> Optional[str]:
        """Return the first non-empty value from a list."""
        if not values:
            return None
        for value in values:
            cleaned = self._clean_text(value)
            if cleaned:
                return cleaned
        return None

    def _looks_like_price(self, value: str) -> bool:
        """Return whether the string looks like a price."""
        normalized = value.lower().strip()
        return bool(re.search(r"\$|usd|price", normalized)) or bool(
            re.fullmatch(r"\d+(?:\.\d{1,2})?", normalized)
        )

    def _looks_like_sales(self, value: str) -> bool:
        """Return whether the string looks like a sales badge."""
        return bool(re.search(r"(?:sold|sales|orders)", value.lower()))

    def _looks_like_rating(self, value: str) -> bool:
        """Return whether the string looks like a rating."""
        return bool(re.search(r"(?:rating|\b[0-5](?:\.\d)?/5\b)", value.lower()))

    async def close(self) -> None:
        """Close is handled by browser pool, no-op here."""
        pass
