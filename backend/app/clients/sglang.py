"""SGLang client for LLM inference."""
import json
from typing import Any, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class SGLangClient:
    """Client for SGLang OpenAI-compatible API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        settings = get_settings()
        self.base_url = base_url or settings.sglang_base_url
        self.model = model or settings.sglang_model
        self.timeout = timeout or settings.sglang_timeout
        self.client = httpx.AsyncClient(timeout=self.timeout)

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        response_format: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Call chat completion endpoint."""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format:
            payload["response_format"] = response_format

        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error("sglang_request_failed", error=str(e), payload=payload)
            raise

    async def generate_structured_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """Generate structured JSON output using JSON schema."""
        messages = [
            {
                "role": "system",
                "content": "You are a helpful assistant that generates structured JSON output.",
            },
            {"role": "user", "content": prompt},
        ]

        response = await self.chat_completion(
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_schema", "json_schema": schema},
        )

        content = response["choices"][0]["message"]["content"]
        return json.loads(content)

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
