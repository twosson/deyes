"""Session coordination for browsing requests."""
from __future__ import annotations

import hashlib
import time
from typing import Iterable

from app.services.browsing.models import BrowserFamilyKey, BrowsingRequest, BrowsingSession, ProxyLease
from app.services.browsing.providers import ProxyProvider


class SessionCoordinator:
    """Resolve browsing requests into reusable logical sessions."""

    def __init__(
        self,
        *,
        proxy_providers: Iterable[ProxyProvider] | None = None,
        sticky_session_ttl_seconds: float = 1800,
    ):
        self._proxy_providers = list(proxy_providers or [])
        self._sticky_session_ttl_seconds = sticky_session_ttl_seconds
        self._sessions: dict[str, BrowsingSession] = {}

    async def acquire_session(self, request: BrowsingRequest) -> BrowsingSession:
        """Resolve a request to a logical browsing session."""
        session_id = self._build_session_id(request)
        now = time.time()
        session = self._sessions.get(session_id)

        if session is None or self._session_expired(session, now):
            session = BrowsingSession(
                session_id=session_id,
                request=request,
                expires_at=self._compute_expiry(request, now),
            )
            self._sessions[session_id] = session

        session.last_used_at = now

        if request.override_proxy_endpoint is None:
            lease = await self._lease_proxy_for_request(request, session)
            if lease is not None:
                session.proxy_lease = lease

        session.browser_family_key = BrowserFamilyKey.from_session(session).render()
        return session

    async def report_success(self, session: BrowsingSession) -> None:
        """Reset failure counters and report success to proxy providers."""
        session.is_healthy = True
        session.failure_count = 0
        session.last_used_at = time.time()
        if session.proxy_lease is not None:
            provider = self._find_provider(session.proxy_lease.provider_name)
            if provider is not None:
                await provider.report_success(session.proxy_lease)

    async def report_failure(self, session: BrowsingSession, error: str | None = None) -> None:
        """Track session failure and notify the proxy provider if one was used."""
        session.failure_count += 1
        session.last_used_at = time.time()
        if session.failure_count >= 3:
            session.is_healthy = False
        if session.proxy_lease is not None:
            provider = self._find_provider(session.proxy_lease.provider_name)
            if provider is not None:
                await provider.report_failure(session.proxy_lease, error=error)

    def get_stats(self) -> dict:
        """Return coordinator and session stats."""
        active_sessions = list(self._sessions.values())
        healthy_count = sum(1 for session in active_sessions if session.is_healthy)
        return {
            "session_count": len(active_sessions),
            "healthy_session_count": healthy_count,
            "unhealthy_session_count": len(active_sessions) - healthy_count,
            "sessions": [
                {
                    "session_id": session.session_id,
                    "target": session.request.target,
                    "region": session.request.region,
                    "workflow": session.request.workflow,
                    "network_mode": session.request.network_mode,
                    "session_scope": session.request.session_scope,
                    "browser_family_key": session.browser_family_key,
                    "proxy_provider": session.proxy_lease.provider_name if session.proxy_lease else None,
                    "proxy_server": session.proxy_lease.endpoint.server if session.proxy_lease else None,
                    "is_healthy": session.is_healthy,
                    "failure_count": session.failure_count,
                    "expires_at": session.expires_at,
                    "last_used_at": session.last_used_at,
                }
                for session in active_sessions
            ],
        }

    async def _lease_proxy_for_request(
        self,
        request: BrowsingRequest,
        session: BrowsingSession,
    ) -> ProxyLease | None:
        """Try providers in order until one leases a proxy for the request."""
        if request.network_mode == "direct":
            return None

        if session.proxy_lease is not None and request.network_mode == "sticky":
            return session.proxy_lease

        sticky_token = session.session_id if request.network_mode == "sticky" else None
        for provider in self._proxy_providers:
            lease = await provider.lease(region=request.region, session_token=sticky_token)
            if lease is not None:
                return lease
        return None

    def _find_provider(self, provider_name: str) -> ProxyProvider | None:
        """Locate a provider by name."""
        for provider in self._proxy_providers:
            if provider.name == provider_name:
                return provider
        return None

    def _session_expired(self, session: BrowsingSession, now: float) -> bool:
        """Return whether a cached session can no longer be reused."""
        return session.expires_at is not None and now >= session.expires_at

    def _compute_expiry(self, request: BrowsingRequest, now: float) -> float | None:
        """Compute the session expiry timestamp from the request scope."""
        if request.session_scope == "request":
            return now
        if request.network_mode == "sticky":
            return now + self._sticky_session_ttl_seconds
        return None

    def _build_session_id(self, request: BrowsingRequest) -> str:
        """Create a stable session key based on request identity semantics."""
        raw = "|".join(
            [
                request.target,
                request.workflow or "default",
                request.region or "default",
                request.network_mode,
                request.session_scope,
                request.identity_hint or "none",
                "persistent" if request.requires_persistence else "ephemeral",
                request.override_proxy_endpoint.server if request.override_proxy_endpoint else "no-override",
            ]
        )
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
        return digest[:20]
