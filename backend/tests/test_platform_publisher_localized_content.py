"""Integration tests for PlatformPublisherAgent localized content feature."""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.platform_publisher import PlatformPublisherAgent
from app.core.enums import (
    CandidateStatus,
    InventoryMode,
    LocalizationType,
    ProductLifecycle,
    ProductMasterStatus,
    ProductVariantStatus,
    SourcePlatform,
    StrategyRunStatus,
    TriggerType,
)
from app.db.models import (
    CandidateProduct,
    ListingDraft,
    LocalizationContent,
    ProductMaster,
    ProductVariant,
    StrategyRun,
)


@pytest.fixture
async def sample_strategy_run_localized(db_session: AsyncSession):
    """Create a sample strategy run for localized tests."""
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.QUEUED,
        max_candidates=5,
    )
    db_session.add(strategy_run)
    await db_session.flush()
    return strategy_run


@pytest.fixture
async def sample_candidate_localized(db_session: AsyncSession, sample_strategy_run_localized):
    """Create a sample candidate product for localized tests."""
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=sample_strategy_run_localized.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        title="Test Product Title",
        status=CandidateStatus.DISCOVERED,
        lifecycle_status=ProductLifecycle.READY_TO_PUBLISH,
        platform_price=Decimal("10.00"),
    )
    db_session.add(candidate)
    await db_session.flush()
    return candidate


@pytest.fixture
async def sample_variant_localized(db_session: AsyncSession, sample_candidate_localized):
    """Create a sample product variant for localized tests."""
    master = ProductMaster(
        id=uuid4(),
        candidate_product_id=sample_candidate_localized.id,
        internal_sku="SKU-LOC-001",
        name="Test Product",
        status=ProductMasterStatus.ACTIVE,
    )
    db_session.add(master)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="SKU-LOC-001",
        inventory_mode=InventoryMode.STOCK_FIRST,
        status=ProductVariantStatus.ACTIVE,
    )
    db_session.add(variant)
    await db_session.flush()
    return variant


@pytest.mark.asyncio
async def test_localized_title_from_listing_draft(
    db_session: AsyncSession, sample_candidate_localized
):
    """Should return localized title from ListingDraft with approved status."""
    # Create German ListingDraft with approved status
    draft = ListingDraft(
        id=uuid4(),
        candidate_product_id=sample_candidate_localized.id,
        language="de",
        title="Deutscher Produkttitel",
        description="Deutsche Produktbeschreibung",
        status="approved",
    )
    db_session.add(draft)
    await db_session.commit()

    # Create agent and call _get_localized_content
    agent = PlatformPublisherAgent()
    title, description = await agent._get_localized_content(
        candidate=sample_candidate_localized,
        variant_id=None,
        language="de",
        db=db_session,
    )

    # Assert returns draft title and description
    assert title == "Deutscher Produkttitel"
    assert description == "Deutsche Produktbeschreibung"


@pytest.mark.asyncio
async def test_localized_description_from_listing_draft(
    db_session: AsyncSession, sample_candidate_localized
):
    """Should return localized description from ListingDraft."""
    # Create ListingDraft with description
    draft = ListingDraft(
        id=uuid4(),
        candidate_product_id=sample_candidate_localized.id,
        language="fr",
        title="Titre du produit français",
        description="Description détaillée du produit en français",
        status="approved",
    )
    db_session.add(draft)
    await db_session.commit()

    # Create agent and call _get_localized_content
    agent = PlatformPublisherAgent()
    title, description = await agent._get_localized_content(
        candidate=sample_candidate_localized,
        variant_id=None,
        language="fr",
        db=db_session,
    )

    # Assert description is returned (not None)
    assert title == "Titre du produit français"
    assert description == "Description détaillée du produit en français"
    assert description is not None


@pytest.mark.asyncio
async def test_fallback_to_localization_content(
    db_session: AsyncSession, sample_candidate_localized, sample_variant_localized
):
    """Should fall back to LocalizationContent when no ListingDraft exists."""
    # No ListingDraft created
    # Create LocalizationContent for variant
    title_loc = LocalizationContent(
        id=uuid4(),
        variant_id=sample_variant_localized.id,
        language="es",
        content_type=LocalizationType.TITLE,
        content={"text": "Título del producto español"},
    )
    desc_loc = LocalizationContent(
        id=uuid4(),
        variant_id=sample_variant_localized.id,
        language="es",
        content_type=LocalizationType.DESCRIPTION,
        content={"text": "Descripción del producto español"},
    )
    db_session.add(title_loc)
    db_session.add(desc_loc)
    await db_session.commit()

    # Create agent and call _get_localized_content
    agent = PlatformPublisherAgent()
    title, description = await agent._get_localized_content(
        candidate=sample_candidate_localized,
        variant_id=sample_variant_localized.id,
        language="es",
        db=db_session,
    )

    # Assert returns localization content
    assert title == "Título del producto español"
    assert description == "Descripción del producto español"


@pytest.mark.asyncio
async def test_fallback_to_english_listing_draft(
    db_session: AsyncSession, sample_candidate_localized
):
    """Should fall back to English ListingDraft when target language not found."""
    # No German ListingDraft
    # Create English ListingDraft
    draft = ListingDraft(
        id=uuid4(),
        candidate_product_id=sample_candidate_localized.id,
        language="en",
        title="English Product Title",
        description="English Product Description",
        status="approved",
    )
    db_session.add(draft)
    await db_session.commit()

    # Create agent and call _get_localized_content with German language
    agent = PlatformPublisherAgent()
    title, description = await agent._get_localized_content(
        candidate=sample_candidate_localized,
        variant_id=None,
        language="de",
        db=db_session,
    )

    # Assert returns English draft content
    assert title == "English Product Title"
    assert description == "English Product Description"


@pytest.mark.asyncio
async def test_fallback_to_english_localization_content(
    db_session: AsyncSession, sample_candidate_localized, sample_variant_localized
):
    """Should fall back to English LocalizationContent when target language not found."""
    # No German LocalizationContent
    # Create English LocalizationContent
    title_loc = LocalizationContent(
        id=uuid4(),
        variant_id=sample_variant_localized.id,
        language="en",
        content_type=LocalizationType.TITLE,
        content={"text": "English Localized Title"},
    )
    desc_loc = LocalizationContent(
        id=uuid4(),
        variant_id=sample_variant_localized.id,
        language="en",
        content_type=LocalizationType.DESCRIPTION,
        content={"text": "English Localized Description"},
    )
    db_session.add(title_loc)
    db_session.add(desc_loc)
    await db_session.commit()

    # Create agent and call _get_localized_content with German language
    agent = PlatformPublisherAgent()
    title, description = await agent._get_localized_content(
        candidate=sample_candidate_localized,
        variant_id=sample_variant_localized.id,
        language="de",
        db=db_session,
    )

    # Assert returns English localization
    assert title == "English Localized Title"
    assert description == "English Localized Description"


@pytest.mark.asyncio
async def test_final_fallback_to_candidate_title(
    db_session: AsyncSession, sample_candidate_localized
):
    """Should fall back to candidate.title when no localization exists."""
    # No ListingDraft, no LocalizationContent
    # Create agent and call _get_localized_content
    agent = PlatformPublisherAgent()
    title, description = await agent._get_localized_content(
        candidate=sample_candidate_localized,
        variant_id=None,
        language="ja",
        db=db_session,
    )

    # Assert returns candidate.title and None description
    assert title == "Test Product Title"
    assert description is None


@pytest.mark.asyncio
async def test_language_inference_from_region():
    """Should infer correct language from region code."""
    agent = PlatformPublisherAgent()

    # Test common region to language mappings
    assert agent._infer_language_from_region("de") == "de"
    assert agent._infer_language_from_region("us") == "en"
    assert agent._infer_language_from_region("uk") == "en"
    assert agent._infer_language_from_region("jp") == "ja"
    assert agent._infer_language_from_region("fr") == "fr"
    assert agent._infer_language_from_region("es") == "es"
    assert agent._infer_language_from_region("it") == "it"
    assert agent._infer_language_from_region("cn") == "zh"
    assert agent._infer_language_from_region("ru") == "ru"
    assert agent._infer_language_from_region("unknown") == "en"  # Default fallback


@pytest.mark.asyncio
async def test_approved_draft_only(
    db_session: AsyncSession, sample_candidate_localized
):
    """Should not use draft with status='draft' (not approved)."""
    # Create draft with status="draft" (not approved)
    draft = ListingDraft(
        id=uuid4(),
        candidate_product_id=sample_candidate_localized.id,
        language="de",
        title="Unapproved German Title",
        description="Unapproved German Description",
        status="draft",  # Not approved
    )
    db_session.add(draft)
    await db_session.commit()

    # Create agent and call _get_localized_content
    agent = PlatformPublisherAgent()
    title, description = await agent._get_localized_content(
        candidate=sample_candidate_localized,
        variant_id=None,
        language="de",
        db=db_session,
    )

    # Assert it's not used, falls back to candidate.title
    assert title == "Test Product Title"
    assert description is None


@pytest.mark.asyncio
async def test_localization_content_structure(
    db_session: AsyncSession, sample_candidate_localized, sample_variant_localized
):
    """Should correctly extract text from LocalizationContent.content dict."""
    # Create LocalizationContent with content dict containing "text" key
    title_loc = LocalizationContent(
        id=uuid4(),
        variant_id=sample_variant_localized.id,
        language="pt",
        content_type=LocalizationType.TITLE,
        content={"text": "Título do produto português", "metadata": "extra_data"},
    )
    db_session.add(title_loc)
    await db_session.commit()

    # Create agent and call _get_localized_content
    agent = PlatformPublisherAgent()
    title, description = await agent._get_localized_content(
        candidate=sample_candidate_localized,
        variant_id=sample_variant_localized.id,
        language="pt",
        db=db_session,
    )

    # Assert correct extraction of text from content dict
    assert title == "Título do produto português"
    assert description is None  # No description localization


@pytest.mark.asyncio
async def test_no_variant_id_skips_localization_content(
    db_session: AsyncSession, sample_candidate_localized, sample_variant_localized
):
    """Should skip LocalizationContent query when variant_id is None."""
    # Create LocalizationContent (should not be queried)
    title_loc = LocalizationContent(
        id=uuid4(),
        variant_id=sample_variant_localized.id,
        language="ru",
        content_type=LocalizationType.TITLE,
        content={"text": "Русский заголовок"},
    )
    db_session.add(title_loc)
    await db_session.commit()

    # Create agent and call _get_localized_content with variant_id=None
    agent = PlatformPublisherAgent()
    title, description = await agent._get_localized_content(
        candidate=sample_candidate_localized,
        variant_id=None,  # No variant_id
        language="ru",
        db=db_session,
    )

    # Assert falls back to candidate.title (LocalizationContent not queried)
    assert title == "Test Product Title"
    assert description is None


@pytest.mark.asyncio
async def test_listing_draft_priority_over_localization(
    db_session: AsyncSession, sample_candidate_localized, sample_variant_localized
):
    """Should prioritize ListingDraft over LocalizationContent."""
    # Create both ListingDraft and LocalizationContent for same language
    draft = ListingDraft(
        id=uuid4(),
        candidate_product_id=sample_candidate_localized.id,
        language="it",
        title="Italian Draft Title",
        description="Italian Draft Description",
        status="approved",
    )
    db_session.add(draft)

    title_loc = LocalizationContent(
        id=uuid4(),
        variant_id=sample_variant_localized.id,
        language="it",
        content_type=LocalizationType.TITLE,
        content={"text": "Italian Localization Title"},
    )
    db_session.add(title_loc)
    await db_session.commit()

    # Create agent and call _get_localized_content
    agent = PlatformPublisherAgent()
    title, description = await agent._get_localized_content(
        candidate=sample_candidate_localized,
        variant_id=sample_variant_localized.id,
        language="it",
        db=db_session,
    )

    # Assert ListingDraft is prioritized
    assert title == "Italian Draft Title"
    assert description == "Italian Draft Description"


@pytest.mark.asyncio
async def test_partial_localization_content(
    db_session: AsyncSession, sample_candidate_localized, sample_variant_localized
):
    """Should handle partial LocalizationContent (only title, no description)."""
    # Create only title LocalizationContent (no description)
    title_loc = LocalizationContent(
        id=uuid4(),
        variant_id=sample_variant_localized.id,
        language="ar",
        content_type=LocalizationType.TITLE,
        content={"text": "عنوان المنتج العربي"},
    )
    db_session.add(title_loc)
    await db_session.commit()

    # Create agent and call _get_localized_content
    agent = PlatformPublisherAgent()
    title, description = await agent._get_localized_content(
        candidate=sample_candidate_localized,
        variant_id=sample_variant_localized.id,
        language="ar",
        db=db_session,
    )

    # Assert title is returned, description is None
    assert title == "عنوان المنتج العربي"
    assert description is None


@pytest.mark.asyncio
async def test_english_fallback_not_triggered_for_english(
    db_session: AsyncSession, sample_candidate_localized
):
    """Should not trigger English fallback when language is already English."""
    # No English ListingDraft exists
    # Create agent and call _get_localized_content with English language
    agent = PlatformPublisherAgent()
    title, description = await agent._get_localized_content(
        candidate=sample_candidate_localized,
        variant_id=None,
        language="en",
        db=db_session,
    )

    # Assert falls back to candidate.title directly (no English fallback logic)
    assert title == "Test Product Title"
    assert description is None
