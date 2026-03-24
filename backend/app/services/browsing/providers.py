"""Proxy provider abstractions for browsing sessions."""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Protocol

from app.services.browsing.models import ProxyEndpoint, ProxyLease


class ProxyProvider(Protocol):
    """Contract for leasing and tracking proxy identities."""

    name: str

    async def lease(
        self,
        *,
        region: str | None = None,
        session_token: str | None = None,
    ) -> ProxyLease | None:
        """Lease a proxy identity for the given browsing need."""

    async def report_success(self, lease: ProxyLease) -> None:
        """Report a successful outcome for the lease."""

    async def report_failure(self, lease: ProxyLease, error: str | None = None) -> None:
        """Report a failed outcome for the lease."""

    def get_stats(self) -> dict:
        """Return provider stats for logs and debugging."""


@dataclass
class StaticProxyRecord:
    """Runtime state for a statically configured proxy endpoint."""

    endpoint: ProxyEndpoint
    region: str | None = None
    healthy: bool = True
    success_count: int = 0
    failure_count: int = 0
    last_used_at: float | None = None


class StaticProxyProvider:
    """Simple round-robin provider backed by a static proxy list."""

    def __init__(self, proxies: list[str] | None = None, *, name: str = "static"):
        self.name = name
        self._records: list[StaticProxyRecord] = []
        self._current_index = 0
        self._sticky_assignments: dict[str, str] = {}
        for proxy in proxies or []:
            self.add_proxy(proxy)

    def add_proxy(self, proxy_url: str) -> None:
        """Add a static proxy URL, optionally tagged as `url#region`."""
        server, region = self._parse_proxy_url(proxy_url)
        if any(record.endpoint.server == server for record in self._records):
            return
        self._records.append(StaticProxyRecord(endpoint=ProxyEndpoint(server=server), region=region))

    async def lease(
        self,
        *,
        region: str | None = None,
        session_token: str | None = None,
    ) -> ProxyLease | None:
        """Lease a healthy static proxy with optional region preference."""
        if not self._records:
            return None

        candidates = self._select_candidates(region)
        if not candidates:
            candidates = self._records

        record = self._pick_record(candidates, session_token=session_token)
        if record is None:
            return None

        record.last_used_at = time.time()
        lease_id = self._build_lease_id(record.endpoint.server, session_token=session_token)
        return ProxyLease(
            lease_id=lease_id,
            provider_name=self.name,
            endpoint=record.endpoint,
            mode="static",
            health_key=record.endpoint.server,
            region=record.region or region,
            session_token=session_token,
            metadata={"provider_type": "static"},
        )

    async def report_success(self, lease: ProxyLease) -> None:
        """Mark the matching static proxy healthy after a success."""
        record = self._find_record(lease.endpoint.server)
        if record is None:
            return
        record.success_count += 1
        record.failure_count = 0
        record.healthy = True
        record.last_used_at = time.time()

    async def report_failure(self, lease: ProxyLease, error: str | None = None) -> None:
        """Mark the matching static proxy unhealthy after repeated failures."""
        record = self._find_record(lease.endpoint.server)
        if record is None:
            return
        record.failure_count += 1
        record.last_used_at = time.time()
        if record.failure_count >= 3:
            record.healthy = False

    def get_stats(self) -> dict:
        """Return static proxy health and usage stats."""
        healthy_count = sum(1 for record in self._records if record.healthy)
        return {
            "provider": self.name,
            "type": "static",
            "proxy_count": len(self._records),
            "healthy_proxy_count": healthy_count,
            "unhealthy_proxy_count": len(self._records) - healthy_count,
            "proxies": [
                {
                    "server": record.endpoint.server,
                    "region": record.region,
                    "healthy": record.healthy,
                    "success_count": record.success_count,
                    "failure_count": record.failure_count,
                    "last_used_at": record.last_used_at,
                }
                for record in self._records
            ],
        }

    def _select_candidates(self, region: str | None) -> list[StaticProxyRecord]:
        """Filter records by requested region while allowing global proxies."""
        if region is None:
            return list(self._records)
        region_lower = region.lower()
        return [
            record
            for record in self._records
            if record.region is None or record.region == region_lower
        ]

    def _pick_record(
        self,
        candidates: list[StaticProxyRecord],
        *,
        session_token: str | None = None,
    ) -> StaticProxyRecord | None:
        """Pick the next healthy record, reusing sticky assignments when possible."""
        if not candidates:
            return None

        if session_token is not None:
            assigned_server = self._sticky_assignments.get(session_token)
            if assigned_server is not None:
                assigned_record = self._find_record(assigned_server)
                if assigned_record is not None and assigned_record in candidates and assigned_record.healthy:
                    return assigned_record

        total_candidates = len(candidates)
        for offset in range(total_candidates):
            record = candidates[(self._current_index + offset) % total_candidates]
            if record.healthy:
                self._current_index = (self._current_index + offset + 1) % total_candidates
                if session_token is not None:
                    self._sticky_assignments[session_token] = record.endpoint.server
                return record

        selected = candidates[0]
        if session_token is not None:
            self._sticky_assignments[session_token] = selected.endpoint.server
        self._current_index = (self._current_index + 1) % total_candidates
        return selected

    def _find_record(self, server: str) -> StaticProxyRecord | None:
        """Find a record by proxy server."""
        for record in self._records:
            if record.endpoint.server == server:
                return record
        return None

    def _parse_proxy_url(self, proxy_url: str) -> tuple[str, str | None]:
        """Parse `url#region` format used by the legacy pool."""
        if "#" not in proxy_url:
            return proxy_url, None
        server, region = proxy_url.rsplit("#", 1)
        return server, region.lower()

    def _build_lease_id(self, server: str, *, session_token: str | None = None) -> str:
        """Create a deterministic lease identifier for static proxies."""
        raw = f"{self.name}:{server}:{session_token or 'none'}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
