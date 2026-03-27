"""Simple validation script for Helium 10 integration.

This script validates the Helium 10 integration without requiring full test environment.
"""
import asyncio
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))


async def test_helium10_client_import():
    """Test that Helium10Client can be imported."""
    try:
        from app.clients.helium10 import Helium10Client
        print("✓ Helium10Client imported successfully")
        return True
    except Exception as e:
        print(f"✗ Failed to import Helium10Client: {e}")
        return False


async def test_helium10_client_init():
    """Test that Helium10Client can be initialized."""
    try:
        from app.clients.helium10 import Helium10Client
        client = Helium10Client(api_key="test_key")
        assert client.api_key == "test_key"
        assert client.cache_ttl_seconds == 86400
        assert client.enable_cache is True
        print("✓ Helium10Client initialized successfully")
        return True
    except Exception as e:
        print(f"✗ Failed to initialize Helium10Client: {e}")
        return False


async def test_demand_validator_import():
    """Test that DemandValidator can be imported."""
    try:
        from app.services.demand_validator import DemandValidator
        print("✓ DemandValidator imported successfully")
        return True
    except Exception as e:
        print(f"✗ Failed to import DemandValidator: {e}")
        return False


async def test_demand_validator_init_with_helium10():
    """Test that DemandValidator can be initialized with Helium 10."""
    try:
        from app.services.demand_validator import DemandValidator
        validator = DemandValidator(
            use_helium10=True,
            helium10_api_key="test_key",
        )
        assert validator.use_helium10 is True
        assert validator.helium10_api_key == "test_key"
        print("✓ DemandValidator initialized with Helium 10 successfully")
        return True
    except Exception as e:
        print(f"✗ Failed to initialize DemandValidator with Helium 10: {e}")
        return False


async def test_region_to_marketplace():
    """Test region to marketplace conversion."""
    try:
        from app.services.demand_validator import DemandValidator
        validator = DemandValidator()

        assert validator._region_to_marketplace("US") == "US"
        assert validator._region_to_marketplace("UK") == "UK"
        assert validator._region_to_marketplace("GB") == "UK"
        assert validator._region_to_marketplace("JP") == "JP"
        assert validator._region_to_marketplace("") == "US"
        assert validator._region_to_marketplace(None) == "US"

        print("✓ Region to marketplace conversion works correctly")
        return True
    except Exception as e:
        print(f"✗ Region to marketplace conversion failed: {e}")
        return False


async def test_cache_key_building():
    """Test cache key building."""
    try:
        from app.clients.helium10 import Helium10Client
        client = Helium10Client(api_key="test_key")

        key1 = client._build_cache_key("phone case", "US")
        key2 = client._build_cache_key("phone case", "UK")
        key3 = client._build_cache_key("wireless charger", "US")

        # Same keyword + marketplace should produce same key
        assert key1 == client._build_cache_key("phone case", "US")

        # Different marketplace should produce different key
        assert key1 != key2

        # Different keyword should produce different key
        assert key1 != key3

        # Key should have expected format
        assert key1.startswith("helium10:")
        assert ":US" in key1

        print("✓ Cache key building works correctly")
        return True
    except Exception as e:
        print(f"✗ Cache key building failed: {e}")
        return False


async def main():
    """Run all validation tests."""
    print("=" * 60)
    print("Helium 10 Integration Validation")
    print("=" * 60)
    print()

    tests = [
        test_helium10_client_import,
        test_helium10_client_init,
        test_demand_validator_import,
        test_demand_validator_init_with_helium10,
        test_region_to_marketplace,
        test_cache_key_building,
    ]

    results = []
    for test in tests:
        result = await test()
        results.append(result)
        print()

    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60)

    if passed == total:
        print("\n✓ All validation tests passed!")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
