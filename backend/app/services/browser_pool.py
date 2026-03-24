"""Browser pool management for high-concurrency scraping."""
from __future__ import annotations

import asyncio
import random
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional
from weakref import WeakSet

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Playwright

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class BrowserInstance:
    """A managed browser instance with its contexts."""

    browser: "Browser"
    playwright: "Playwright"
    created_at: float = field(default_factory=time.time)
    contexts: WeakSet["BrowserContext"] = field(default_factory=WeakSet)
    request_count: int = 0
    active_context_count: int = 0
    last_used_at: float = field(default_factory=time.time)
    is_healthy: bool = True
    retiring: bool = False
    failure_count: int = 0
    last_error_at: Optional[float] = None

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    @property
    def idle_seconds(self) -> float:
        return time.time() - self.last_used_at


@dataclass
class Fingerprint:
    """Browser fingerprint configuration."""

    user_agent: str
    viewport: dict
    locale: str
    timezone: str
    platform: str
    webgl_vendor: str
    webgl_renderer: str
    canvas_noise: bool = True
    audio_noise: bool = True


@dataclass
class ProxyConfig:
    """Proxy configuration with region metadata."""

    url: str
    region: Optional[str] = None  # e.g., 'us', 'uk', 'de'
    success_count: int = 0
    failure_count: int = 0
    last_used_at: float = 0
    is_healthy: bool = True


class FingerprintManager:
    """Generate and manage browser fingerprints."""

    USER_AGENTS = [
        # Chrome on macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        # Chrome on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        # Chrome on Linux
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    ]

    VIEWPORTS = [
        {"width": 1920, "height": 1080},
        {"width": 1680, "height": 1050},
        {"width": 1440, "height": 900},
        {"width": 1536, "height": 864},
        {"width": 1366, "height": 768},
    ]

    REGION_CONFIGS = {
        "us": {
            "timezones": ["America/New_York", "America/Los_Angeles", "America/Chicago"],
            "locales": ["en-US"],
        },
        "uk": {
            "timezones": ["Europe/London"],
            "locales": ["en-GB"],
        },
        "ca": {
            "timezones": ["America/Toronto", "America/Vancouver"],
            "locales": ["en-CA", "fr-CA"],
        },
        "de": {
            "timezones": ["Europe/Berlin"],
            "locales": ["de-DE"],
        },
        "fr": {
            "timezones": ["Europe/Paris"],
            "locales": ["fr-FR"],
        },
        "jp": {
            "timezones": ["Asia/Tokyo"],
            "locales": ["ja-JP"],
        },
    }

    DEFAULT_TIMEZONES = [
        "America/New_York",
        "America/Los_Angeles",
        "America/Chicago",
        "Europe/London",
        "Europe/Paris",
        "Asia/Tokyo",
    ]

    DEFAULT_LOCALES = ["en-US", "en-GB", "en-CA"]

    PLATFORMS = {
        "Macintosh": "MacIntel",
        "Windows": "Win32",
        "Linux": "Linux x86_64",
    }

    WEBGL_CONFIGS = [
        ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0)"),
        ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1080 Direct3D11 vs_5_0 ps_5_0)"),
        ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0)"),
        ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0)"),
        ("Apple Inc.", "Apple GPU"),
    ]

    def generate(self, region: Optional[str] = None) -> Fingerprint:
        """Generate a random browser fingerprint, optionally for a specific region.

        Args:
            region: Target region code (e.g., 'us', 'uk'). If None, uses default settings.
        """
        ua = random.choice(self.USER_AGENTS)
        viewport = random.choice(self.VIEWPORTS)

        # Get region-specific settings
        if region and region.lower() in self.REGION_CONFIGS:
            region_config = self.REGION_CONFIGS[region.lower()]
            timezone = random.choice(region_config["timezones"])
            locale = random.choice(region_config["locales"])
        else:
            # Infer platform from UA for default behavior
            if "Macintosh" in ua:
                timezone = random.choice(["America/New_York", "America/Los_Angeles"])
            elif "Windows" in ua:
                timezone = random.choice(["America/New_York", "America/Chicago"])
            else:
                timezone = random.choice(["America/Los_Angeles", "Europe/London"])
            locale = random.choice(self.DEFAULT_LOCALES)

        # Infer platform from UA
        if "Macintosh" in ua:
            platform = "MacIntel"
        elif "Windows" in ua:
            platform = "Win32"
        else:
            platform = "Linux x86_64"

        webgl_vendor, webgl_renderer = random.choice(self.WEBGL_CONFIGS)

        return Fingerprint(
            user_agent=ua,
            viewport=viewport,
            locale=locale,
            timezone=timezone,
            platform=platform,
            webgl_vendor=webgl_vendor,
            webgl_renderer=webgl_renderer,
            canvas_noise=random.random() > 0.3,
            audio_noise=random.random() > 0.3,
        )


class ProxyManager:
    """Manage proxy pool for scraping with region awareness."""

    def __init__(self, proxy_list: Optional[list[str]] = None):
        self.proxies: list[ProxyConfig] = []
        self.current_index = 0
        if proxy_list:
            for proxy in proxy_list:
                self.add_proxy(proxy)

    def _parse_proxy_url(self, proxy_url: str) -> tuple[str, Optional[str]]:
        """Parse proxy URL and extract region tag if present.

        Format: http://proxy.com:8080#us or http://proxy.com:8080
        """
        if "#" in proxy_url:
            url, region = proxy_url.rsplit("#", 1)
            return url, region.lower()
        return proxy_url, None

    def get_proxy(self, region: Optional[str] = None) -> Optional[str]:
        """Get next available proxy using round-robin with health check and region filtering.

        Args:
            region: Target region code (e.g., 'us', 'uk'). If None, returns any healthy proxy.
        """
        if not self.proxies:
            return None

        # Filter by region if specified
        candidates = self.proxies
        if region:
            region_lower = region.lower()
            candidates = [p for p in self.proxies if p.region == region_lower or p.region is None]
            if not candidates:
                # No region-specific proxies, fall back to all proxies
                candidates = self.proxies

        # Find healthy proxy
        for _ in range(len(candidates)):
            proxy_config = candidates[self.current_index % len(candidates)]
            self.current_index = (self.current_index + 1) % len(self.proxies)

            if proxy_config.is_healthy:
                return proxy_config.url

        # All proxies unhealthy, return first one anyway
        return candidates[0].url if candidates else None

    def mark_success(self, proxy_url: str):
        """Mark proxy as successful."""
        for proxy_config in self.proxies:
            if proxy_config.url == proxy_url:
                proxy_config.success_count += 1
                proxy_config.last_used_at = time.time()
                proxy_config.is_healthy = True
                proxy_config.failure_count = 0  # Reset failure count on success
                break

    def mark_failure(self, proxy_url: str):
        """Mark proxy as failed."""
        for proxy_config in self.proxies:
            if proxy_config.url == proxy_url:
                proxy_config.failure_count += 1
                # Mark unhealthy after 3 consecutive failures
                if proxy_config.failure_count >= 3:
                    proxy_config.is_healthy = False
                break

    def add_proxy(self, proxy_url: str):
        """Add a proxy to the pool.

        Args:
            proxy_url: Proxy URL, optionally with region tag (e.g., 'http://proxy.com:8080#us')
        """
        url, region = self._parse_proxy_url(proxy_url)

        # Check if already exists
        if any(p.url == url for p in self.proxies):
            return

        self.proxies.append(ProxyConfig(url=url, region=region))


class BrowserPool:
    """Manage a pool of browser instances for concurrent scraping."""

    _instance: Optional["BrowserPool"] = None
    _lock = asyncio.Lock()

    def __init__(
        self,
        max_browsers: int = 3,
        max_contexts_per_browser: int = 5,
        browser_max_age_seconds: float = 1800,
        context_max_age_seconds: float = 300,
        idle_timeout_seconds: float = 60,
        browser_failure_threshold: int = 3,
        cleanup_interval_seconds: float = 60,
    ):
        self.settings = get_settings()
        self.logger = get_logger(__name__)

        self.max_browsers = max_browsers
        self.max_contexts_per_browser = max_contexts_per_browser
        self.browser_max_age_seconds = browser_max_age_seconds
        self.context_max_age_seconds = context_max_age_seconds
        self.idle_timeout_seconds = idle_timeout_seconds
        self.browser_failure_threshold = browser_failure_threshold
        self.cleanup_interval_seconds = cleanup_interval_seconds

        self.browsers: list[BrowserInstance] = []
        self.fingerprint_manager = FingerprintManager()
        self.proxy_manager = ProxyManager()

        self._semaphore = asyncio.Semaphore(max_browsers * max_contexts_per_browser)
        self._initialized = False
        self._cleanup_task: Optional[asyncio.Task] = None
        self._pool_lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls, **kwargs) -> "BrowserPool":
        """Get singleton instance of browser pool."""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = BrowserPool(**kwargs)
                    await cls._instance.initialize()
        return cls._instance

    @classmethod
    async def shutdown(cls):
        """Shutdown the browser pool."""
        if cls._instance is not None:
            await cls._instance.close()
            cls._instance = None

    async def initialize(self):
        """Initialize the browser pool."""
        if self._initialized:
            return

        self.logger.info(
            "browser_pool_initializing",
            max_browsers=self.max_browsers,
            max_contexts_per_browser=self.max_contexts_per_browser,
        )

        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._initialized = True
        self.logger.info("browser_pool_initialized")

    async def _create_browser(self) -> BrowserInstance:
        """Create a new browser instance."""
        from playwright.async_api import async_playwright

        playwright = await async_playwright().start()

        browser = await playwright.chromium.launch(
            headless=self.settings.scraper_headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-site-isolation-trials",
                "--disable-web-security",
                "--disable-features=ImprovedCookieControls",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        instance = BrowserInstance(browser=browser, playwright=playwright)

        self.logger.info(
            "browser_created",
            browser_count=len(self.browsers) + 1,
        )

        return instance

    async def _create_context(
        self,
        browser_instance: BrowserInstance,
        fingerprint: Optional[Fingerprint] = None,
        proxy: Optional[str] = None,
        region: Optional[str] = None,
    ) -> "BrowserContext":
        """Create a new browser context with fingerprint."""
        if fingerprint is None:
            fingerprint = self.fingerprint_manager.generate(region=region)

        context_args = {
            "viewport": fingerprint.viewport,
            "user_agent": fingerprint.user_agent,
            "locale": fingerprint.locale,
            "timezone_id": fingerprint.timezone,
            "java_script_enabled": True,
            "bypass_csp": True,
            "ignore_https_errors": True,
        }

        if proxy:
            context_args["proxy"] = {"server": proxy}

        context = await browser_instance.browser.new_context(**context_args)

        try:
            await self._inject_stealth_scripts(context, fingerprint)
        except Exception:
            try:
                await context.close()
            except Exception:
                pass
            raise

        browser_instance.contexts.add(context)

        self.logger.debug(
            "context_created",
            fingerprint_user_agent=fingerprint.user_agent[:50],
            active_context_count=browser_instance.active_context_count,
        )

        return context

    async def _inject_stealth_scripts(self, context: "BrowserContext", fingerprint: Fingerprint):
        """Inject scripts to hide automation fingerprints."""
        await context.add_init_script(
            f"""
            // Override navigator.webdriver
            Object.defineProperty(navigator, 'webdriver', {{
                get: () => undefined
            }});

            // Override navigator.platform
            Object.defineProperty(navigator, 'platform', {{
                get: () => '{fingerprint.platform}'
            }});

            // Override navigator.hardwareConcurrency
            Object.defineProperty(navigator, 'hardwareConcurrency', {{
                get: () => {random.randint(4, 16)}
            }});

            // Override navigator.deviceMemory
            Object.defineProperty(navigator, 'deviceMemory', {{
                get: () => {random.randint(4, 16)}
            }});

            // Override WebGL
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {{
                if (parameter === 37445) return '{fingerprint.webgl_vendor}';
                if (parameter === 37446) return '{fingerprint.webgl_renderer}';
                return getParameter.call(this, parameter);
            }};

            // Override canvas fingerprint
            const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.toDataURL = function(type) {{
                if (this.width === 220 && this.height === 30) {{
                    // Common fingerprint canvas size, add noise
                    const ctx = this.getContext('2d');
                    if (ctx) {{
                        const imageData = ctx.getImageData(0, 0, this.width, this.height);
                        for (let i = 0; i < imageData.data.length; i += 4) {{
                            imageData.data[i] ^= (Math.random() * 2) | 0;
                        }}
                        ctx.putImageData(imageData, 0, 0);
                    }}
                }}
                return originalToDataURL.apply(this, arguments);
            }};

            // Hide automation indicators
            window.chrome = {{
                runtime: {{}}
            }};

            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({{ state: Notification.permission }}) :
                    originalQuery(parameters)
            );
            """
        )

    @asynccontextmanager
    async def get_page(
        self,
        fingerprint: Optional[Fingerprint] = None,
        proxy: Optional[str] = None,
        region: Optional[str] = None,
    ):
        """Get a page from the browser pool.

        Usage:
            async with pool.get_page() as page:
                await page.goto("https://example.com")
                # ... do scraping ...
        """
        async with self._semaphore:
            browser_instance: Optional[BrowserInstance] = None
            context = None
            page = None

            try:
                browser_instance = await self._get_available_browser()

                if proxy is None and self.proxy_manager.proxies:
                    proxy = self.proxy_manager.get_proxy(region=region)

                try:
                    context = await self._create_context(
                        browser_instance,
                        fingerprint,
                        proxy,
                        region=region,
                    )
                except Exception as exc:
                    await self._record_browser_failure(browser_instance, exc, stage="create_context")
                    raise

                try:
                    page = await context.new_page()
                except Exception as exc:
                    await self._record_browser_failure(browser_instance, exc, stage="new_page")
                    raise

                await self._record_browser_success(browser_instance)
                yield page

                if proxy:
                    self.proxy_manager.mark_success(proxy)

            except Exception as exc:
                if proxy:
                    self.proxy_manager.mark_failure(proxy)

                self.logger.warning(
                    "browser_pool_page_error",
                    error=str(exc),
                )
                raise

            finally:
                if page:
                    try:
                        await page.close()
                    except Exception:
                        pass

                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass

                if browser_instance:
                    await self._release_browser_slot(browser_instance)

    async def _get_available_browser(self) -> BrowserInstance:
        """Get an available browser instance or create a new one."""
        for attempt in range(2):
            browsers_to_close: list[tuple[BrowserInstance, str]] = []
            selected_browser: Optional[BrowserInstance] = None

            async with self._pool_lock:
                browsers_to_close = self._retire_and_detach_browsers_locked()
                selected_browser = self._reserve_available_browser_locked()

                if selected_browser is None and len(self.browsers) < self.max_browsers:
                    browser_instance = await self._create_browser()
                    self.browsers.append(browser_instance)
                    selected_browser = self._reserve_browser_slot_locked(browser_instance)

            for browser_instance, reason in browsers_to_close:
                await self._close_browser_instance(browser_instance, reason)

            if selected_browser is not None:
                return selected_browser

            if attempt == 0:
                await asyncio.sleep(0.5)
                await self._cleanup_old_browsers()

        raise RuntimeError("No available browser instances in pool")

    def _reserve_available_browser_locked(self) -> Optional[BrowserInstance]:
        """Reserve a slot on an existing browser while holding the pool lock."""
        for browser_instance in self.browsers:
            if browser_instance.retiring or not browser_instance.is_healthy:
                continue

            if browser_instance.active_context_count >= self.max_contexts_per_browser:
                continue

            return self._reserve_browser_slot_locked(browser_instance)

        return None

    def _reserve_browser_slot_locked(self, browser_instance: BrowserInstance) -> BrowserInstance:
        """Reserve one context slot for a browser while holding the pool lock."""
        browser_instance.active_context_count += 1
        browser_instance.request_count += 1
        browser_instance.last_used_at = time.time()
        return browser_instance

    def _get_retirement_reason(self, browser_instance: BrowserInstance) -> Optional[str]:
        """Return the reason a browser should retire, if any."""
        if not browser_instance.is_healthy:
            return "unhealthy"

        if browser_instance.age_seconds > self.browser_max_age_seconds:
            return "max_age"

        if (
            browser_instance.active_context_count == 0
            and browser_instance.idle_seconds > self.idle_timeout_seconds
        ):
            return "idle_timeout"

        return None

    def _retire_and_detach_browsers_locked(self) -> list[tuple[BrowserInstance, str]]:
        """Mark browsers as retiring and detach drained browsers while holding the pool lock."""
        browsers_to_close: list[tuple[BrowserInstance, str]] = []

        for browser_instance in list(self.browsers):
            close_reason: Optional[str] = None

            if browser_instance.retiring:
                if browser_instance.active_context_count == 0:
                    close_reason = "retired_drained"
            else:
                retirement_reason = self._get_retirement_reason(browser_instance)
                if retirement_reason is not None:
                    browser_instance.retiring = True
                    self.logger.info(
                        "browser_retiring",
                        reason=retirement_reason,
                        active_context_count=browser_instance.active_context_count,
                        age_seconds=browser_instance.age_seconds,
                        failure_count=browser_instance.failure_count,
                    )
                    if browser_instance.active_context_count == 0:
                        close_reason = retirement_reason

            if close_reason is not None:
                self.browsers.remove(browser_instance)
                browsers_to_close.append((browser_instance, close_reason))

        return browsers_to_close

    async def _release_browser_slot(self, browser_instance: BrowserInstance):
        """Release a reserved slot and close drained retiring browsers."""
        browser_to_close: Optional[BrowserInstance] = None

        async with self._pool_lock:
            if browser_instance.active_context_count > 0:
                browser_instance.active_context_count -= 1

            browser_instance.last_used_at = time.time()

            if (
                browser_instance in self.browsers
                and browser_instance.retiring
                and browser_instance.active_context_count == 0
            ):
                self.browsers.remove(browser_instance)
                browser_to_close = browser_instance

        if browser_to_close is not None:
            await self._close_browser_instance(browser_to_close, "retired_drained")

    async def _record_browser_success(self, browser_instance: BrowserInstance):
        """Reset transient browser failure state after a successful allocation."""
        async with self._pool_lock:
            if browser_instance.retiring:
                return

            browser_instance.failure_count = 0
            browser_instance.last_error_at = None
            browser_instance.last_used_at = time.time()

    async def _record_browser_failure(
        self,
        browser_instance: BrowserInstance,
        error: Exception,
        stage: str,
    ):
        """Record browser-instance failures and retire unhealthy browsers."""
        browser_to_close: Optional[BrowserInstance] = None
        failure_count = 0
        active_context_count = 0
        marked_unhealthy = False

        async with self._pool_lock:
            browser_instance.failure_count += 1
            browser_instance.last_error_at = time.time()
            browser_instance.last_used_at = browser_instance.last_error_at

            failure_count = browser_instance.failure_count
            active_context_count = browser_instance.active_context_count
            marked_unhealthy = failure_count >= self.browser_failure_threshold

            if marked_unhealthy:
                browser_instance.is_healthy = False
                browser_instance.retiring = True

                if (
                    browser_instance in self.browsers
                    and browser_instance.active_context_count == 0
                ):
                    self.browsers.remove(browser_instance)
                    browser_to_close = browser_instance

        if marked_unhealthy:
            self.logger.warning(
                "browser_marked_unhealthy",
                stage=stage,
                error=str(error),
                failure_count=failure_count,
                failure_threshold=self.browser_failure_threshold,
                active_context_count=active_context_count,
            )
        else:
            self.logger.warning(
                "browser_failure_recorded",
                stage=stage,
                error=str(error),
                failure_count=failure_count,
                failure_threshold=self.browser_failure_threshold,
                active_context_count=active_context_count,
            )

        if browser_to_close is not None:
            await self._close_browser_instance(browser_to_close, "unhealthy")

    async def _close_browser_instance(self, browser_instance: BrowserInstance, reason: str):
        """Close a detached browser instance."""
        try:
            await browser_instance.browser.close()
        except Exception:
            pass

        try:
            await browser_instance.playwright.stop()
        except Exception:
            pass

        self.logger.info(
            "browser_removed",
            reason=reason,
            remaining_browsers=len(self.browsers),
            age_seconds=browser_instance.age_seconds,
            request_count=browser_instance.request_count,
            failure_count=browser_instance.failure_count,
        )

    async def _cleanup_old_browsers(self):
        """Retire old or unhealthy browsers and close any that are already drained."""
        async with self._pool_lock:
            browsers_to_close = self._retire_and_detach_browsers_locked()

        for browser_instance, reason in browsers_to_close:
            await self._close_browser_instance(browser_instance, reason)

    async def _cleanup_loop(self):
        """Periodically cleanup old browsers."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval_seconds)
                await self._cleanup_old_browsers()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.logger.warning("browser_cleanup_error", error=str(exc))

    async def close(self):
        """Close all browser instances."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        async with self._pool_lock:
            browsers_to_close = list(self.browsers)
            self.browsers.clear()
            self._initialized = False

        for browser_instance in browsers_to_close:
            browser_instance.retiring = True
            await self._close_browser_instance(browser_instance, "shutdown")

        self.logger.info("browser_pool_closed")

    def add_proxies(self, proxies: list[str]):
        """Add proxies to the pool."""
        for proxy in proxies:
            self.proxy_manager.add_proxy(proxy)

    def get_stats(self) -> dict:
        """Get pool statistics."""
        browser_summaries = []
        active_context_count_total = 0
        healthy_browser_count = 0
        retiring_browser_count = 0
        unhealthy_browser_count = 0

        for index, browser_instance in enumerate(self.browsers):
            active_context_count_total += browser_instance.active_context_count

            if browser_instance.retiring:
                retiring_browser_count += 1
            if not browser_instance.is_healthy:
                unhealthy_browser_count += 1
            if browser_instance.is_healthy and not browser_instance.retiring:
                healthy_browser_count += 1

            browser_summaries.append(
                {
                    "index": index,
                    "active_context_count": browser_instance.active_context_count,
                    "request_count": browser_instance.request_count,
                    "age_seconds": round(browser_instance.age_seconds, 2),
                    "idle_seconds": round(browser_instance.idle_seconds, 2),
                    "retiring": browser_instance.retiring,
                    "is_healthy": browser_instance.is_healthy,
                    "failure_count": browser_instance.failure_count,
                    "last_error_at": browser_instance.last_error_at,
                    "tracked_context_count": len(browser_instance.contexts),
                }
            )

        healthy_proxy_count = sum(1 for proxy in self.proxy_manager.proxies if proxy.is_healthy)

        return {
            "browser_count": len(self.browsers),
            "max_browsers": self.max_browsers,
            "max_contexts_per_browser": self.max_contexts_per_browser,
            "browser_failure_threshold": self.browser_failure_threshold,
            "cleanup_interval_seconds": self.cleanup_interval_seconds,
            "active_context_count_total": active_context_count_total,
            "healthy_browser_count": healthy_browser_count,
            "retiring_browser_count": retiring_browser_count,
            "unhealthy_browser_count": unhealthy_browser_count,
            "browsers": browser_summaries,
            "proxy_count": len(self.proxy_manager.proxies),
            "healthy_proxy_count": healthy_proxy_count,
            "unhealthy_proxy_count": len(self.proxy_manager.proxies) - healthy_proxy_count,
        }
