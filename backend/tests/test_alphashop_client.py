"""Tests for AlphaShop API client."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.clients.alphashop import AlphaShopClient


class TestAlphaShopClient:
    """Test AlphaShopClient."""

    def test_init_requires_credentials(self):
        """Test initialization requires both access key and secret key."""
        with pytest.raises(ValueError, match="access key is required"):
            AlphaShopClient(access_key="", secret_key="test_secret")

        with pytest.raises(ValueError, match="secret key is required"):
            AlphaShopClient(access_key="test_key", secret_key="")

    def test_init_with_valid_credentials(self):
        """Test initialization with valid credentials."""
        client = AlphaShopClient(
            access_key="test_key",
            secret_key="test_secret",
            base_url="https://api.example.com",
            timeout=60,
            max_retries=5,
        )

        assert client.access_key == "test_key"
        assert client.secret_key == "test_secret"
        assert client.base_url == "https://api.example.com"
        assert client.timeout == 60
        assert client.max_retries == 5

    def test_build_authorization_header(self):
        """Test JWT authorization header generation."""
        client = AlphaShopClient(
            access_key="test_key",
            secret_key="test_secret",
        )

        header = client._build_authorization_header()

        assert header.startswith("Bearer ")
        assert len(header) > 10

    def test_create_api_token_caching(self):
        """Test JWT token is cached and reused."""
        client = AlphaShopClient(
            access_key="test_key",
            secret_key="test_secret",
        )

        token1 = client._create_api_token()
        token2 = client._create_api_token()

        # Should return same cached token
        assert token1 == token2

    @pytest.mark.asyncio
    async def test_search_keywords_success(self):
        """Test successful keyword search with model list response."""
        client = AlphaShopClient(
            access_key="test_key",
            secret_key="test_secret",
        )

        mock_response = {
            "resultCode": "SUCCESS",
            "model": [
                {
                    "keyword": "phone case",
                    "searchVolume": 5000,
                    "oppScore": 75,
                }
            ],
        }

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            result = await client.search_keywords(
                platform="amazon",
                region="US",
                keyword="phone case",
                listing_time="180",
            )

        assert "keyword_list" in result
        assert len(result["keyword_list"]) == 1
        assert result["keyword_list"][0]["keyword"] == "phone case"
        assert result["keyword_list"][0]["searchVolume"] == 5000

    @pytest.mark.asyncio
    async def test_search_keywords_normalizes_platform_for_alphashop(self):
        """Test keyword.search sends AlphaShop's documented platform casing."""
        client = AlphaShopClient(
            access_key="test_key",
            secret_key="test_secret",
        )

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"resultCode": "SUCCESS", "model": []}

            await client.search_keywords(
                platform="temu",
                region="US",
                keyword="phone case",
                listing_time="180",
            )

        mock_request.assert_awaited_once_with(
            client.KEYWORD_SEARCH_ENDPOINT,
            {
                "platform": "Amazon",
                "region": "US",
                "keyword": "phone case",
                "listingTime": "180",
            },
        )
    @pytest.mark.asyncio
    async def test_search_keywords_with_data_variant(self):
        """Test keyword search with data-list variant response."""
        client = AlphaShopClient(
            access_key="test_key",
            secret_key="test_secret",
        )

        mock_response = {
            "code": "SUCCESS",
            "data": [
                {"keyword": "wireless earbuds", "searchRank": 500, "oppScore": 80},
                {"keyword": "bluetooth speaker", "searchRank": 2000, "oppScore": 65},
            ],
        }

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            result = await client.search_keywords(
                platform="amazon",
                region="US",
                keyword="electronics",
                listing_time="90",
            )

        assert "keyword_list" in result
        assert len(result["keyword_list"]) == 2
        assert result["keyword_list"][0]["keyword"] == "wireless earbuds"


    @pytest.mark.asyncio
    async def test_newproduct_report_success(self):
        """Test successful newproduct.report normalization."""
        client = AlphaShopClient(
            access_key="test_key",
            secret_key="test_secret",
        )

        mock_response = {
            "resultCode": "SUCCESS",
            "requestId": "req-789",
            "model": {
                "productList": [
                    {
                        "productId": "p1",
                        "title": "Trending Phone Stand",
                    }
                ],
                "keywordSummary": {
                    "summary": "Rising demand with moderate competition",
                    "opportunityScore": 82,
                },
            },
        }

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            result = await client.newproduct_report(
                platform="amazon",
                region="US",
                product_keyword="phone stand",
                listing_time="180",
                size=10,
            )

        assert result["request_id"] == "req-789"
        assert len(result["product_list"]) == 1
        assert result["items"] == result["product_list"]
        assert result["product_list"][0]["title"] == "Trending Phone Stand"
        assert result["keyword_summary"]["opportunityScore"] == 82

    @pytest.mark.asyncio
    async def test_newproduct_report_normalizes_platform_for_alphashop(self):
        """Test newproduct.report sends AlphaShop's documented platform casing."""
        client = AlphaShopClient(
            access_key="test_key",
            secret_key="test_secret",
        )

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {
                "resultCode": "SUCCESS",
                "model": {"productList": [], "keywordSummary": {}},
            }

            await client.newproduct_report(
                platform="amazon",
                region="US",
                product_keyword="phone stand",
                listing_time="180",
                size=10,
            )

        call_args = mock_request.call_args
        assert call_args[0][1]["platform"] == "Amazon"
        assert call_args[0][1]["productKeyword"] == "phone stand"

    @pytest.mark.asyncio
    async def test_search_supplier_info_success(self):
        client = AlphaShopClient(
            access_key="test_key",
            secret_key="test_secret",
        )

        mock_response = {
            "resultCode": "SUCCESS",
            "result": {
                "data": [
                    {"companyName": "Factory Co.", "shopUrl": "https://shop.1688.com/factory"},
                ]
            },
        }

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            result = await client.search_supplier_info(company="Factory Co.")

        assert "suppliers" in result
        assert len(result["suppliers"]) == 1
        assert result["suppliers"][0]["companyName"] == "Factory Co."

    @pytest.mark.asyncio
    async def test_submit_batch_inquiry_success(self):
        """Test successful batch inquiry submission."""
        client = AlphaShopClient(
            access_key="test_key",
            secret_key="test_secret",
        )

        mock_response = {
            "resultCode": "SUCCESS",
            "result": {
                "data": "task-abc-123",
                "traceId": "trace-xyz",
            },
        }

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            result = await client.submit_batch_inquiry(
                question_list=["MOQ?", "Lead time?"],
                item_list=["item-1", "item-2"],
            )

        assert result["task_id"] == "task-abc-123"
        assert result["trace_id"] == "trace-xyz"

    @pytest.mark.asyncio
    async def test_query_inquiry_result_success(self):
        """Test successful inquiry result query."""
        client = AlphaShopClient(
            access_key="test_key",
            secret_key="test_secret",
        )

        mock_response = {
            "resultCode": "SUCCESS",
            "result": {
                "data": {
                    "status": "completed",
                    "replies": [{"itemId": "item-1", "reply": "MOQ is 100 pcs"}],
                }
            },
        }

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            result = await client.query_inquiry_result(task_id="task-abc-123")

        assert "data" in result
        assert result["data"]["status"] == "completed"

    def test_ensure_success_passes_on_success_code(self):
        """Test _ensure_success passes on SUCCESS code."""
        client = AlphaShopClient(
            access_key="test_key",
            secret_key="test_secret",
        )

        # Should not raise
        client._ensure_success({"resultCode": "SUCCESS", "success": True}, endpoint="/test")

    def test_ensure_success_raises_on_error_code(self):
        """Test _ensure_success raises on error code."""
        client = AlphaShopClient(
            access_key="test_key",
            secret_key="test_secret",
        )

        with pytest.raises(RuntimeError, match="AlphaShop API error"):
            client._ensure_success(
                {"resultCode": "FAIL_BUSINESS_ERROR", "msg": "Invalid request"},
                endpoint="/test",
            )

    def test_ensure_success_raises_on_false_success(self):
        """Test _ensure_success raises when success is False."""
        client = AlphaShopClient(
            access_key="test_key",
            secret_key="test_secret",
        )

        with pytest.raises(RuntimeError):
            client._ensure_success(
                {"resultCode": "SUCCESS", "success": False, "msg": "Server error"},
                endpoint="/test",
            )

    def test_extract_keyword_list_from_model_list(self):
        """Test keyword list extraction from model array."""
        client = AlphaShopClient(
            access_key="test_key",
            secret_key="test_secret",
        )

        response = {
            "model": [
                {"keyword": "phone case", "searchVolume": 5000},
                {"keyword": "laptop stand", "searchVolume": 3000},
            ]
        }

        result = client._extract_keyword_list(response)

        assert len(result) == 2
        assert result[0]["keyword"] == "phone case"
        assert result[1]["keyword"] == "laptop stand"

    def test_extract_keyword_list_from_model_dict(self):
        """Test keyword list extraction from model dict with keywordList."""
        client = AlphaShopClient(
            access_key="test_key",
            secret_key="test_secret",
        )

        response = {
            "model": {
                "keywordList": [
                    {"keyword": "bluetooth speaker", "oppScore": 70},
                ]
            }
        }

        result = client._extract_keyword_list(response)

        assert len(result) == 1
        assert result[0]["keyword"] == "bluetooth speaker"

    def test_extract_keyword_list_from_nested_result(self):
        """Test keyword list extraction from nested result.data structure."""
        client = AlphaShopClient(
            access_key="test_key",
            secret_key="test_secret",
        )

        response = {
            "result": {
                "data": {
                    "keywordList": [
                        {"keyword": "usb cable", "searchRank": "# 1000+"},
                    ]
                }
            }
        }

        result = client._extract_keyword_list(response)

        assert len(result) == 1
        assert result[0]["keyword"] == "usb cable"

    def test_extract_keyword_list_empty_on_unknown_structure(self):
        """Test keyword list extraction returns empty list for unknown structures."""
        client = AlphaShopClient(
            access_key="test_key",
            secret_key="test_secret",
        )

        response = {"unknownField": "value"}
        result = client._extract_keyword_list(response)

        assert result == []

    @pytest.mark.asyncio
    async def test_request_retries_on_retryable_error(self):
        """Test that _request retries on retryable error codes."""
        client = AlphaShopClient(
            access_key="test_key",
            secret_key="test_secret",
            max_retries=3,
        )

        # Create a mock HTTP client that fails twice then succeeds
        mock_http_client = AsyncMock()
        error_response = MagicMock()
        error_response.json.return_value = {
            "resultCode": "FAIL_TRIGGER_QPS_LIMIT_POLICY",
            "msg": "Rate limited",
        }
        success_response = MagicMock()
        success_response.json.return_value = {"resultCode": "SUCCESS", "success": True}
        success_response.raise_for_status = MagicMock()

        error_response.raise_for_status = MagicMock()

        mock_http_client.post.side_effect = [
            error_response,
            error_response,
            success_response,
        ]

        with patch.object(client, "_get_http_client", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_http_client

            result = await client._request("/test", {})

        # Should have been called 3 times (2 failures + 1 success)
        assert mock_http_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_close(self):
        """Test close releases HTTP client."""
        client = AlphaShopClient(
            access_key="test_key",
            secret_key="test_secret",
        )

        mock_http_client = AsyncMock()
        client._http_client = mock_http_client

        await client.close()

        mock_http_client.aclose.assert_called_once()
        assert client._http_client is None
