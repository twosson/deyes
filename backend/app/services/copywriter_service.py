"""Multilingual copywriter service using SGLang."""
from typing import Any

from app.clients.sglang import SGLangClient
from app.core.logging import get_logger

logger = get_logger(__name__)


class CopywriterService:
    """Service for generating multilingual listing copy."""

    def __init__(self, sglang_client: SGLangClient):
        self.client = sglang_client

    async def generate_listing_copy(
        self,
        product_context: dict[str, Any],
        language: str,
    ) -> dict[str, Any]:
        """Generate listing copy for a single language."""
        prompt = self._build_prompt(product_context, language)
        schema = self._get_output_schema()

        try:
            result = await self.client.generate_structured_json(
                prompt=prompt,
                schema=schema,
                temperature=0.7,
            )

            logger.info(
                "listing_copy_generated",
                language=language,
                product_title=product_context.get("title"),
            )

            return result
        except Exception as e:
            logger.error(
                "listing_copy_generation_failed",
                error=str(e),
                language=language,
                product_title=product_context.get("title"),
            )
            raise

    async def generate_multilingual_copy(
        self,
        product_context: dict[str, Any],
        languages: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Generate listing copy for multiple languages."""
        results = {}

        for language in languages:
            try:
                copy = await self.generate_listing_copy(product_context, language)
                results[language] = copy
            except Exception as e:
                logger.error(
                    "multilingual_copy_generation_failed",
                    error=str(e),
                    language=language,
                )
                # Continue with other languages even if one fails
                results[language] = {"error": str(e)}

        return results

    def _build_prompt(self, product_context: dict[str, Any], language: str) -> str:
        """Build prompt for copywriting."""
        title = product_context.get("title", "")
        category = product_context.get("category", "")
        platform_price = product_context.get("platform_price", "")
        key_features = product_context.get("key_features", [])

        language_names = {
            "en": "English",
            "es": "Spanish",
            "ja": "Japanese",
            "ru": "Russian",
            "pt": "Portuguese",
            "de": "German",
            "fr": "French",
            "it": "Italian",
        }

        lang_name = language_names.get(language, language)

        prompt = f"""You are an expert e-commerce copywriter. Generate compelling product listing copy in {lang_name}.

Product Information:
- Title: {title}
- Category: {category}
- Price: ${platform_price}
- Key Features: {', '.join(key_features) if key_features else 'Not provided'}

Requirements:
1. Title: 60-80 characters, include main keywords, compelling and clear
2. Bullets: 3-5 bullet points highlighting key benefits and features
3. Description: 2-3 paragraphs describing the product, its benefits, and use cases
4. SEO Keywords: 5-8 relevant keywords for search optimization

Write in {lang_name}. Focus on benefits, not just features. Use persuasive language that drives conversions.
"""

        return prompt

    def _get_output_schema(self) -> dict[str, Any]:
        """Get JSON schema for structured output."""
        return {
            "name": "listing_copy",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Product listing title (60-80 characters)",
                    },
                    "bullets": {
                        "type": "array",
                        "description": "3-5 bullet points highlighting key features",
                        "items": {"type": "string"},
                    },
                    "description": {
                        "type": "string",
                        "description": "Full product description (2-3 paragraphs)",
                    },
                    "seo_keywords": {
                        "type": "array",
                        "description": "5-8 SEO keywords",
                        "items": {"type": "string"},
                    },
                },
                "required": ["title", "bullets", "description", "seo_keywords"],
                "additionalProperties": False,
            },
        }
