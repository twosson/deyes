"""Validation script for Stage 5 first batch implementation.

Verifies:
1. PlatformListing model has marketplace field
2. PlatformRegistry is initialized correctly
3. UnifiedListingService can be instantiated
4. Backward compatibility with existing code
"""
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))


def validate_model_changes():
    """Validate PlatformListing model changes."""
    print("✓ Validating PlatformListing model...")

    from app.db.models import PlatformListing
    from sqlalchemy import inspect

    # Check marketplace field exists
    mapper = inspect(PlatformListing)
    columns = {col.key for col in mapper.columns}

    assert "marketplace" in columns, "marketplace field not found"
    assert "platform" in columns, "platform field not found"
    assert "region" in columns, "region field not found"
    assert "platform_listing_id" in columns, "platform_listing_id field not found"

    print("  ✓ marketplace field exists")
    print("  ✓ All required fields present")


def validate_platform_registry():
    """Validate PlatformRegistry implementation."""
    print("\n✓ Validating PlatformRegistry...")

    from app.services.platform_registry import (
        PlatformRegistry,
        PlatformCapability,
        get_platform_registry,
    )
    from app.core.enums import TargetPlatform

    # Get registry instance
    registry = get_platform_registry()
    assert isinstance(registry, PlatformRegistry), "Registry not initialized"

    # Check supported platforms
    platforms = registry.get_supported_platforms()
    assert TargetPlatform.TEMU in platforms, "Temu not registered"
    assert TargetPlatform.AMAZON in platforms, "Amazon not registered"
    assert TargetPlatform.OZON in platforms, "Ozon not registered"

    print(f"  ✓ {len(platforms)} platforms registered")

    # Check capabilities
    assert registry.supports_feature(
        TargetPlatform.TEMU, PlatformCapability.CREATE_LISTING
    ), "Temu should support create_listing"

    assert registry.supports_feature(
        TargetPlatform.TEMU, PlatformCapability.UPDATE_LISTING
    ), "Temu should support update_listing"

    print("  ✓ Capability checking works")

    # Check adapter resolution
    adapter = registry.get_adapter(TargetPlatform.TEMU, "us")
    assert adapter is not None, "Failed to get Temu adapter"
    assert adapter.platform == TargetPlatform.TEMU, "Wrong platform"

    print("  ✓ Adapter resolution works")


def validate_unified_listing_service():
    """Validate UnifiedListingService implementation."""
    print("\n✓ Validating UnifiedListingService...")

    from app.services.unified_listing_service import UnifiedListingService

    # Instantiate service
    service = UnifiedListingService()
    assert service is not None, "Failed to instantiate service"

    # Check methods exist
    assert hasattr(service, "create_listing"), "create_listing method missing"
    assert hasattr(service, "update_listing"), "update_listing method missing"
    assert hasattr(service, "sync_listing"), "sync_listing method missing"
    assert hasattr(service, "get_listing_snapshot"), "get_listing_snapshot method missing"
    assert hasattr(service, "get_sku_listings"), "get_sku_listings method missing"
    assert hasattr(service, "get_platform_listings"), "get_platform_listings method missing"

    print("  ✓ All required methods present")


def validate_backward_compatibility():
    """Validate backward compatibility with existing code."""
    print("\n✓ Validating backward compatibility...")

    from app.services.platforms import get_platform_adapter
    from app.core.enums import TargetPlatform

    # Old function should still work
    adapter = get_platform_adapter(TargetPlatform.TEMU, "us")
    assert adapter is not None, "Old get_platform_adapter function broken"
    assert adapter.platform == TargetPlatform.TEMU, "Wrong platform"

    print("  ✓ get_platform_adapter() still works")

    # Check existing services still work
    from app.services.listing_activation_service import ListingActivationService
    from app.services.platform_sync_service import PlatformSyncService

    activation_service = ListingActivationService()
    assert activation_service is not None, "ListingActivationService broken"

    sync_service = PlatformSyncService()
    assert sync_service is not None, "PlatformSyncService broken"

    print("  ✓ Existing services still work")


def validate_migration_file():
    """Validate migration file exists and is well-formed."""
    print("\n✓ Validating migration file...")

    migration_file = backend_path / "migrations" / "versions" / "20260329_1800_013_platform_listing_multiplatform.py"
    assert migration_file.exists(), f"Migration file not found: {migration_file}"

    # Read migration content
    content = migration_file.read_text()
    assert "marketplace" in content, "Migration doesn't add marketplace field"
    assert "idx_platform_marketplace_listing" in content, "Missing composite index"
    assert "idx_variant_platform_region" in content, "Missing variant index"
    assert "def upgrade()" in content, "Missing upgrade function"
    assert "def downgrade()" in content, "Missing downgrade function"

    print("  ✓ Migration file exists and is well-formed")


def main():
    """Run all validations."""
    print("=" * 60)
    print("Stage 5 First Batch Implementation Validation")
    print("=" * 60)

    try:
        validate_model_changes()
        validate_platform_registry()
        validate_unified_listing_service()
        validate_backward_compatibility()
        validate_migration_file()

        print("\n" + "=" * 60)
        print("✅ All validations passed!")
        print("=" * 60)
        print("\nStage 5 First Batch Implementation Summary:")
        print("  ✓ Task A1: PlatformListing model extended")
        print("  ✓ Task A2: PlatformRegistry implemented")
        print("  ✓ Task A3: UnifiedListingService implemented")
        print("  ✓ Migration 013 created")
        print("  ✓ Backward compatibility maintained")
        print("\nNext steps:")
        print("  1. Run database migration: alembic upgrade head")
        print("  2. Run tests: pytest tests/test_stage5_batch1.py -v")
        print("  3. Proceed to Stage 5 second batch (A4, B1, C1)")

        return 0

    except Exception as e:
        print(f"\n❌ Validation failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
