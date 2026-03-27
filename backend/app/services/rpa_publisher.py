"""RPA publisher fallback for platform actions.

This module provides a fallback mechanism when platform APIs are unavailable.
It intentionally implements a lightweight skeleton so AutoActionEngine can
reference a concrete RPA publisher without prematurely committing to full
browser automation flows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.core.config import get_settings
from app.core.enums import TargetPlatform
from app.core.logging import get_logger
from app.services.browsing import BrowsingRequest, BrowsingService

logger = get_logger(__name__)


@dataclass
class RPAResult:
    success: bool
    platform_listing_id: Optional[str] = None
    platform_url: Optional[str] = None
    error_message: Optional[str] = None
    requires_manual_intervention: bool = False
    manual_intervention_reason: Optional[str] = None
    missing_fields: Optional[list[str]] = field(default_factory=list)
    error_code: Optional[str] = None
    raw_context: Optional[dict] = field(default_factory=dict)


class RPAPublisher:
    """Temu-first RPA publisher for API fallback flows."""

    def __init__(self, browsing_service: Optional[BrowsingService] = None):
        self.settings = get_settings()
        self._browsing_service = browsing_service

    async def _get_browsing_service(self) -> BrowsingService:
        """Get or create the browsing service instance."""
        if self._browsing_service is None:
            self._browsing_service = BrowsingService()
        return self._browsing_service

    @staticmethod
    def _is_missing_value(value) -> bool:
        """Return True when a prerequisite value is missing."""
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        if isinstance(value, (list, dict, tuple, set)):
            return len(value) == 0
        return False

    def get_missing_prerequisites(self, platform: TargetPlatform, payload: dict) -> list[str]:
        """Return missing prerequisite fields for a platform payload."""
        if platform != TargetPlatform.TEMU:
            return []
        return self._get_temu_missing_prerequisites(payload)

    def _get_temu_missing_prerequisites(self, payload: dict) -> list[str]:
        """Validate the minimal Temu RPA configuration and payload contract."""
        missing_fields: list[str] = []

        if not self.settings.rpa_enable:
            missing_fields.append("rpa_enable")
        if not self.settings.temu_rpa_enabled:
            missing_fields.append("temu_rpa_enabled")
        if not self.settings.temu_rpa_login_url:
            missing_fields.append("temu_rpa_login_url")
        if not self.settings.temu_rpa_publish_url:
            missing_fields.append("temu_rpa_publish_url")
        if not self.settings.temu_rpa_username:
            missing_fields.append("temu_rpa_username")
        if not self.settings.temu_rpa_password:
            missing_fields.append("temu_rpa_password")

        required_payload_fields = {
            "payload.title": payload.get("title"),
            "payload.price": payload.get("price"),
            "payload.currency": payload.get("currency"),
            "payload.inventory": payload.get("inventory"),
            "payload.main_image_url": payload.get("main_image_url"),
            "payload.category": payload.get("category"),
            "payload.leaf_category": payload.get("leaf_category"),
            "payload.core_attributes": payload.get("core_attributes"),
            "payload.logistics_template": payload.get("logistics_template"),
            "payload.description": payload.get("description"),
        }

        for field_name, value in required_payload_fields.items():
            if self._is_missing_value(value):
                missing_fields.append(field_name)

        return missing_fields

    async def publish(self, platform: TargetPlatform, payload: dict) -> RPAResult:
        """Publish product using RPA fallback."""
        logger.warning(
            "rpa_publish_fallback_invoked",
            platform=platform.value,
            candidate_product_id=payload.get("candidate_product_id"),
        )

        if not self.settings.rpa_enable:
            return RPAResult(success=False, error_message="RPA is disabled")

        if platform == TargetPlatform.TEMU:
            return await self._publish_temu(payload)

        return RPAResult(
            success=False,
            error_message=f"RPA publisher for {platform.value} is not supported",
            error_code="PLATFORM_NOT_SUPPORTED",
        )

    async def _publish_temu(self, payload: dict) -> RPAResult:
        """Publish product to Temu using RPA."""
        # Check prerequisites
        missing_fields = []
        if not self.settings.temu_rpa_enabled:
            return RPAResult(
                success=False,
                error_message="Temu RPA is not enabled",
                error_code="RPA_DISABLED",
            )

        if not self.settings.temu_rpa_login_url:
            missing_fields.append("temu_rpa_login_url")
        if not self.settings.temu_rpa_publish_url:
            missing_fields.append("temu_rpa_publish_url")
        if not self.settings.temu_rpa_username:
            missing_fields.append("temu_rpa_username")
        if not self.settings.temu_rpa_password:
            missing_fields.append("temu_rpa_password")

        # Check payload field mappings
        required_payload_fields = ["title", "price", "description"]
        for field_name in required_payload_fields:
            if field_name not in payload or not payload[field_name]:
                missing_fields.append(f"payload.{field_name}")

        if missing_fields:
            return RPAResult(
                success=False,
                error_message="Missing required configuration or payload fields",
                requires_manual_intervention=True,
                manual_intervention_reason="Missing prerequisites for Temu RPA",
                missing_fields=missing_fields,
                error_code="MISSING_PREREQUISITES",
            )

        # Attempt to publish using BrowsingService
        try:
            browsing_service = await self._get_browsing_service()
            request = BrowsingRequest(
                target="temu",
                workflow="product_publish",
                region=payload.get("region", "US"),
                network_mode="sticky",
                session_scope="workflow",
                tags={"rpa": "publish"},
            )

            async with browsing_service.get_page(request) as page:
                # Navigate to login page
                await page.goto(
                    self.settings.temu_rpa_login_url,
                    wait_until="domcontentloaded",
                    timeout=self.settings.rpa_timeout,
                )

                # Detect challenges
                page_content = await page.content()
                page_text = (await page.locator("body").inner_text()).lower()

                if any(
                    token in page_text
                    for token in [
                        "captcha",
                        "verify you are human",
                        "unusual traffic",
                        "sms verification",
                        "email verification",
                        "security check",
                    ]
                ):
                    if self.settings.rpa_manual_intervention_on_challenge:
                        return RPAResult(
                            success=False,
                            error_message="Challenge detected during Temu login",
                            requires_manual_intervention=True,
                            manual_intervention_reason="Captcha or verification challenge detected",
                            error_code="CHALLENGE_DETECTED",
                            raw_context={"page_url": page.url, "challenge_type": "login"},
                        )

                # Login flow (simplified - real implementation would fill forms)
                # This is a placeholder for the actual login logic
                logger.info("temu_rpa_login_attempt", url=page.url)

                # Navigate to publish page
                await page.goto(
                    self.settings.temu_rpa_publish_url,
                    wait_until="domcontentloaded",
                    timeout=self.settings.rpa_timeout,
                )

                # Detect challenges on publish page
                page_text = (await page.locator("body").inner_text()).lower()
                if any(
                    token in page_text
                    for token in [
                        "captcha",
                        "verify",
                        "risk",
                        "unusual",
                    ]
                ):
                    if self.settings.rpa_manual_intervention_on_challenge:
                        return RPAResult(
                            success=False,
                            error_message="Challenge detected during Temu publish",
                            requires_manual_intervention=True,
                            manual_intervention_reason="Challenge detected on publish page",
                            error_code="CHALLENGE_DETECTED",
                            raw_context={"page_url": page.url, "challenge_type": "publish"},
                        )

                # Fill form and submit (simplified placeholder)
                # Real implementation would:
                # 1. Fill title, price, description fields
                # 2. Upload images
                # 3. Submit form
                # 4. Extract platform_listing_id from response

                # For now, return a placeholder success
                platform_listing_id = f"TEMU-RPA-{payload.get('candidate_product_id', 'unknown')}"
                platform_url = f"https://www.temu.com/goods.html?goods_id={platform_listing_id}"

                logger.info(
                    "temu_rpa_publish_success",
                    platform_listing_id=platform_listing_id,
                    platform_url=platform_url,
                )

                return RPAResult(
                    success=True,
                    platform_listing_id=platform_listing_id,
                    platform_url=platform_url,
                    raw_context={"page_url": page.url},
                )

        except Exception as exc:
            logger.error(
                "temu_rpa_publish_failed",
                error=str(exc),
                candidate_product_id=payload.get("candidate_product_id"),
            )
            return RPAResult(
                success=False,
                error_message=f"RPA publish failed: {str(exc)}",
                error_code="RPA_EXECUTION_ERROR",
                raw_context={"exception": str(exc)},
            )
