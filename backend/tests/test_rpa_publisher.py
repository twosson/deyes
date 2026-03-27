"""Tests for RPAPublisher."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.enums import TargetPlatform
from app.services.rpa_publisher import RPAPublisher, RPAResult


@pytest.mark.asyncio
async def test_temu_prerequisites_check_missing_config():
    """Test Temu prerequisites check returns manual intervention when config missing."""
    with patch("app.services.rpa_publisher.get_settings") as mock_settings:
        settings = MagicMock()
        settings.rpa_enable = True
        settings.temu_rpa_enabled = True
        settings.temu_rpa_login_url = ""  # Missing
        settings.temu_rpa_publish_url = ""  # Missing
        settings.temu_rpa_username = ""  # Missing
        settings.temu_rpa_password = ""  # Missing
        settings.rpa_manual_intervention_on_challenge = True
        mock_settings.return_value = settings

        publisher = RPAPublisher()
        payload = {
            "candidate_product_id": "test-123",
            "title": "Test Product",
            "price": "10.00",
            "description": "Test description",
        }

        result = await publisher.publish(TargetPlatform.TEMU, payload)

        assert result.success is False
        assert result.requires_manual_intervention is True
        assert result.error_code == "MISSING_PREREQUISITES"
        assert "temu_rpa_login_url" in result.missing_fields
        assert "temu_rpa_publish_url" in result.missing_fields
        assert "temu_rpa_username" in result.missing_fields
        assert "temu_rpa_password" in result.missing_fields


@pytest.mark.asyncio
async def test_temu_prerequisites_check_missing_payload_fields():
    """Test Temu prerequisites check returns manual intervention when payload fields missing."""
    with patch("app.services.rpa_publisher.get_settings") as mock_settings:
        settings = MagicMock()
        settings.rpa_enable = True
        settings.temu_rpa_enabled = True
        settings.temu_rpa_login_url = "https://seller.temu.com/login"
        settings.temu_rpa_publish_url = "https://seller.temu.com/publish"
        settings.temu_rpa_username = "test_user"
        settings.temu_rpa_password = "test_pass"
        settings.rpa_manual_intervention_on_challenge = True
        mock_settings.return_value = settings

        publisher = RPAPublisher()
        payload = {
            "candidate_product_id": "test-123",
            # Missing title, price, description
        }

        result = await publisher.publish(TargetPlatform.TEMU, payload)

        assert result.success is False
        assert result.requires_manual_intervention is True
        assert result.error_code == "MISSING_PREREQUISITES"
        assert "payload.title" in result.missing_fields
        assert "payload.price" in result.missing_fields
        assert "payload.description" in result.missing_fields


@pytest.mark.asyncio
async def test_temu_challenge_detection_returns_manual_intervention():
    """Test challenge detection returns manual intervention."""
    with patch("app.services.rpa_publisher.get_settings") as mock_settings:
        settings = MagicMock()
        settings.rpa_enable = True
        settings.temu_rpa_enabled = True
        settings.temu_rpa_login_url = "https://seller.temu.com/login"
        settings.temu_rpa_publish_url = "https://seller.temu.com/publish"
        settings.temu_rpa_username = "test_user"
        settings.temu_rpa_password = "test_pass"
        settings.rpa_manual_intervention_on_challenge = True
        settings.rpa_timeout = 30000
        mock_settings.return_value = settings

        # Mock BrowsingService
        mock_browsing_service = AsyncMock()
        mock_page = AsyncMock()
        mock_page.url = "https://seller.temu.com/login"
        mock_page.content = AsyncMock(return_value="<html><body>Please verify you are human</body></html>")
        mock_locator = AsyncMock()
        mock_locator.inner_text = AsyncMock(return_value="Please verify you are human captcha")
        mock_page.locator = MagicMock(return_value=mock_locator)
        mock_browsing_service.get_page = MagicMock()
        mock_browsing_service.get_page.return_value.__aenter__ = AsyncMock(return_value=mock_page)
        mock_browsing_service.get_page.return_value.__aexit__ = AsyncMock(return_value=None)

        publisher = RPAPublisher(browsing_service=mock_browsing_service)
        payload = {
            "candidate_product_id": "test-123",
            "title": "Test Product",
            "price": "10.00",
            "description": "Test description",
            "region": "US",
        }

        result = await publisher.publish(TargetPlatform.TEMU, payload)

        assert result.success is False
        assert result.requires_manual_intervention is True
        assert result.error_code == "CHALLENGE_DETECTED"
        assert "captcha" in result.manual_intervention_reason.lower() or "verification" in result.manual_intervention_reason.lower()
        assert result.raw_context is not None
        assert "challenge_type" in result.raw_context


@pytest.mark.asyncio
async def test_unsupported_platform_returns_error():
    """Test unsupported platform returns error."""
    with patch("app.services.rpa_publisher.get_settings") as mock_settings:
        settings = MagicMock()
        settings.rpa_enable = True
        mock_settings.return_value = settings

        publisher = RPAPublisher()
        payload = {"candidate_product_id": "test-123"}

        result = await publisher.publish(TargetPlatform.AMAZON, payload)

        assert result.success is False
        assert result.error_code == "PLATFORM_NOT_SUPPORTED"
        assert "not supported" in result.error_message.lower()


@pytest.mark.asyncio
async def test_rpa_disabled_returns_error():
    """Test RPA disabled returns error."""
    with patch("app.services.rpa_publisher.get_settings") as mock_settings:
        settings = MagicMock()
        settings.rpa_enable = False
        mock_settings.return_value = settings

        publisher = RPAPublisher()
        payload = {"candidate_product_id": "test-123"}

        result = await publisher.publish(TargetPlatform.TEMU, payload)

        assert result.success is False
        assert "disabled" in result.error_message.lower()


@pytest.mark.asyncio
async def test_temu_rpa_disabled_returns_error():
    """Test Temu RPA disabled returns error."""
    with patch("app.services.rpa_publisher.get_settings") as mock_settings:
        settings = MagicMock()
        settings.rpa_enable = True
        settings.temu_rpa_enabled = False
        mock_settings.return_value = settings

        publisher = RPAPublisher()
        payload = {
            "candidate_product_id": "test-123",
            "title": "Test Product",
            "price": "10.00",
            "description": "Test description",
        }

        result = await publisher.publish(TargetPlatform.TEMU, payload)

        assert result.success is False
        assert result.error_code == "RPA_DISABLED"
        assert "not enabled" in result.error_message.lower()


@pytest.mark.asyncio
async def test_temu_success_flow():
    """Test successful Temu publish flow."""
    with patch("app.services.rpa_publisher.get_settings") as mock_settings:
        settings = MagicMock()
        settings.rpa_enable = True
        settings.temu_rpa_enabled = True
        settings.temu_rpa_login_url = "https://seller.temu.com/login"
        settings.temu_rpa_publish_url = "https://seller.temu.com/publish"
        settings.temu_rpa_username = "test_user"
        settings.temu_rpa_password = "test_pass"
        settings.rpa_manual_intervention_on_challenge = True
        settings.rpa_timeout = 30000
        mock_settings.return_value = settings

        # Mock BrowsingService with no challenges
        mock_browsing_service = AsyncMock()
        mock_page = AsyncMock()
        mock_page.url = "https://seller.temu.com/publish"
        mock_page.content = AsyncMock(return_value="<html><body>Publish form</body></html>")
        mock_locator = AsyncMock()
        mock_locator.inner_text = AsyncMock(return_value="Publish your product here")
        mock_page.locator = MagicMock(return_value=mock_locator)
        mock_browsing_service.get_page = MagicMock()
        mock_browsing_service.get_page.return_value.__aenter__ = AsyncMock(return_value=mock_page)
        mock_browsing_service.get_page.return_value.__aexit__ = AsyncMock(return_value=None)

        publisher = RPAPublisher(browsing_service=mock_browsing_service)
        payload = {
            "candidate_product_id": "test-123",
            "title": "Test Product",
            "price": "10.00",
            "description": "Test description",
            "region": "US",
        }

        result = await publisher.publish(TargetPlatform.TEMU, payload)

        assert result.success is True
        assert result.platform_listing_id is not None
        assert "TEMU-RPA" in result.platform_listing_id
        assert result.platform_url is not None
        assert result.requires_manual_intervention is False
