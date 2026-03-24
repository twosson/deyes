"""Browsing service for managing browser sessions, proxies, and page allocation."""
from app.services.browsing.models import (
    BrowserFamilyKey,
    BrowsingNetworkMode,
    BrowsingRequest,
    BrowsingSession,
    BrowsingSessionScope,
    ProxyEndpoint,
    ProxyLease,
    ProxyLeaseMode,
)
from app.services.browsing.providers import ProxyProvider, StaticProxyProvider
from app.services.browsing.runtime import BrowserRuntime
from app.services.browsing.service import BrowsingService
from app.services.browsing.session_coordinator import SessionCoordinator

__all__ = [
    "BrowserFamilyKey",
    "BrowserRuntime",
    "BrowsingNetworkMode",
    "BrowsingRequest",
    "BrowsingService",
    "BrowsingSession",
    "BrowsingSessionScope",
    "ProxyEndpoint",
    "ProxyLease",
    "ProxyLeaseMode",
    "ProxyProvider",
    "SessionCoordinator",
    "StaticProxyProvider",
]
