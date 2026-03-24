"""Domain models for browsing, sessions, and proxy leases."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

BrowsingNetworkMode = Literal["direct", "rotating", "sticky"]
BrowsingSessionScope = Literal["request", "workflow", "job"]
ProxyLeaseMode = Literal["direct", "rotating", "sticky", "static"]


@dataclass(frozen=True)
class ProxyEndpoint:
    """Playwright-ready proxy configuration."""

    server: str
    username: str | None = None
    password: str | None = None
    bypass: str | None = None

    def to_playwright_dict(self) -> dict[str, str]:
        """Convert proxy endpoint to Playwright launch arguments."""
        payload = {"server": self.server}
        if self.username:
            payload["username"] = self.username
        if self.password:
            payload["password"] = self.password
        if self.bypass:
            payload["bypass"] = self.bypass
        return payload


@dataclass(frozen=True)
class ProxyLease:
    """A leased network identity from a proxy provider."""

    lease_id: str
    provider_name: str
    endpoint: ProxyEndpoint
    mode: ProxyLeaseMode
    health_key: str
    region: str | None = None
    session_token: str | None = None
    expires_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrowsingRequest:
    """A request for browsing capabilities."""

    target: str
    workflow: str | None = None
    region: str | None = None
    network_mode: BrowsingNetworkMode = "sticky"
    session_scope: BrowsingSessionScope = "request"
    requires_persistence: bool = False
    identity_hint: str | None = None
    override_proxy_endpoint: ProxyEndpoint | None = None
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class BrowsingSession:
    """Logical browsing identity used to acquire and reuse browser families."""

    session_id: str
    request: BrowsingRequest
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    last_used_at: float = field(default_factory=time.time)
    proxy_lease: ProxyLease | None = None
    browser_family_key: str = ""
    is_healthy: bool = True
    failure_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrowserFamilyKey:
    """Stable key describing a browser family that can safely share runtime state."""

    target: str
    region: str | None
    network_mode: BrowsingNetworkMode
    identity_key: str

    def render(self) -> str:
        """Render the family key as a string for maps and logs."""
        return "|".join(
            [
                self.target,
                self.region or "default",
                self.network_mode,
                self.identity_key,
            ]
        )

    @classmethod
    def from_session(cls, session: BrowsingSession) -> "BrowserFamilyKey":
        """Build a browser family key from a resolved browsing session."""
        lease = session.proxy_lease
        request = session.request

        if request.override_proxy_endpoint is not None:
            identity_key = f"override:{request.override_proxy_endpoint.server}"
        elif lease is None:
            identity_key = "direct"
        elif lease.mode == "sticky":
            identity_key = f"session:{lease.session_token or session.session_id}"
        elif lease.mode == "static":
            identity_key = f"proxy:{lease.health_key}"
        else:
            identity_key = f"provider:{lease.provider_name}:{lease.region or request.region or 'default'}"

        return cls(
            target=request.target,
            region=request.region,
            network_mode=request.network_mode,
            identity_key=identity_key,
        )
