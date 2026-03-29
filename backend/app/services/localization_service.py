"""Localization service for managing product variant content."""
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import LocalizationType
from app.core.logging import get_logger
from app.db.models import LocalizationContent

logger = get_logger(__name__)


class LocalizationService:
    """Service for managing localization content."""

    async def create_localization(
        self,
        *,
        variant_id: UUID,
        language: str,
        content_type: LocalizationType,
        content: dict,
        db: AsyncSession,
        platform_tags: Optional[list[str]] = None,
        region_tags: Optional[list[str]] = None,
        quality_score: Optional[float] = None,
        generated_by: Optional[str] = None,
    ) -> LocalizationContent:
        """Create or update localization content (idempotent).

        Args:
            variant_id: Product variant ID
            language: Language code (e.g., "en", "zh")
            content_type: Type of content (title, description, etc.)
            content: Content data as dict
            db: Database session
            platform_tags: Optional platform tags
            region_tags: Optional region tags
            quality_score: Optional quality score (0.0-1.0)
            generated_by: Optional generator identifier

        Returns:
            LocalizationContent instance
        """
        # Check if localization already exists
        existing = await self.get_localization(
            variant_id=variant_id,
            language=language,
            content_type=content_type,
            db=db,
        )

        if existing:
            # Update existing
            existing.content = content
            existing.platform_tags = platform_tags
            existing.region_tags = region_tags
            if quality_score is not None:
                existing.quality_score = quality_score
            if generated_by:
                existing.generated_by = generated_by

            await db.flush()
            logger.info(
                "localization_updated",
                localization_id=str(existing.id),
                variant_id=str(variant_id),
                language=language,
                content_type=content_type.value,
            )
            return existing

        # Create new
        localization = LocalizationContent(
            id=uuid4(),
            variant_id=variant_id,
            language=language,
            content_type=content_type,
            content=content,
            platform_tags=platform_tags,
            region_tags=region_tags,
            quality_score=quality_score,
            generated_by=generated_by,
            reviewed=False,
        )

        db.add(localization)
        await db.flush()

        logger.info(
            "localization_created",
            localization_id=str(localization.id),
            variant_id=str(variant_id),
            language=language,
            content_type=content_type.value,
        )

        return localization

    async def get_localization(
        self,
        *,
        variant_id: UUID,
        language: str,
        content_type: LocalizationType,
        db: AsyncSession,
    ) -> Optional[LocalizationContent]:
        """Get localization content by variant, language, and type.

        Args:
            variant_id: Product variant ID
            language: Language code
            content_type: Type of content
            db: Database session

        Returns:
            LocalizationContent if found, None otherwise
        """
        stmt = select(LocalizationContent).where(
            LocalizationContent.variant_id == variant_id,
            LocalizationContent.language == language,
            LocalizationContent.content_type == content_type,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_localizations(
        self,
        *,
        variant_id: UUID,
        db: AsyncSession,
        language: Optional[str] = None,
        content_type: Optional[LocalizationType] = None,
        platform: Optional[str] = None,
        region: Optional[str] = None,
    ) -> list[LocalizationContent]:
        """List all localizations for a variant with optional filters.

        Args:
            variant_id: Product variant ID
            db: Database session
            language: Optional language filter
            content_type: Optional content type filter
            platform: Optional platform filter
            region: Optional region filter

        Returns:
            List of LocalizationContent instances
        """
        stmt = select(LocalizationContent).where(LocalizationContent.variant_id == variant_id)

        if language:
            stmt = stmt.where(LocalizationContent.language == language)
        if content_type:
            stmt = stmt.where(LocalizationContent.content_type == content_type)
        if platform:
            stmt = stmt.where(LocalizationContent.platform_tags.contains([platform]))
        if region:
            stmt = stmt.where(LocalizationContent.region_tags.contains([region]))

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def update_localization(
        self,
        *,
        localization_id: UUID,
        content: dict,
        db: AsyncSession,
        quality_score: Optional[float] = None,
        reviewed: Optional[bool] = None,
    ) -> Optional[LocalizationContent]:
        """Update localization content.

        Args:
            localization_id: Localization ID
            content: New content data
            db: Database session
            quality_score: Optional new quality score
            reviewed: Optional reviewed flag

        Returns:
            Updated LocalizationContent if found, None otherwise
        """
        localization = await db.get(LocalizationContent, localization_id)
        if not localization:
            return None

        localization.content = content
        if quality_score is not None:
            localization.quality_score = quality_score
        if reviewed is not None:
            localization.reviewed = reviewed

        await db.flush()

        logger.info(
            "localization_updated",
            localization_id=str(localization_id),
            variant_id=str(localization.variant_id),
        )

        return localization

    async def delete_localization(
        self,
        *,
        localization_id: UUID,
        db: AsyncSession,
    ) -> bool:
        """Delete localization content.

        Args:
            localization_id: Localization ID
            db: Database session

        Returns:
            True if deleted, False if not found
        """
        localization = await db.get(LocalizationContent, localization_id)
        if not localization:
            return False

        await db.delete(localization)
        await db.flush()

        logger.info(
            "localization_deleted",
            localization_id=str(localization_id),
        )

        return True
