"""
Scraper for challenge.place tournament pages.
Uses Playwright (headless Chromium) because the site is a JS-rendered SPA.
Results are cached for CACHE_TTL seconds to avoid hammering the site.
"""

import asyncio
import time
import logging
from typing import Optional
from playwright.async_api import async_playwright, Page

logger = logging.getLogger(__name__)

CACHE_TTL = 300  # 5 minutes


class ChallengeScraper:
    def __init__(self, tournament_url: str):
        self.base_url = tournament_url.rstrip("/")
        self._cache: dict[str, tuple[str, float]] = {}  # {key: (data, timestamp)}

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_all_data(self) -> dict:
        """Fetch all tournament data in one shot (parallelised)."""
        dashboard, standings, statistics, competitors = await asyncio.gather(
            self._cached("dashboard", self._scrape_dashboard),
            self._cached("standings", self._scrape_standings),
            self._cached("statistics", self._scrape_statistics),
            self._cached("competitors", self._scrape_competitors),
        )
        return {
            "dashboard": dashboard,
            "standings": standings,
            "statistics": statistics,
            "competitors": competitors,
        }

    # ── Cache wrapper ─────────────────────────────────────────────────────────

    async def _cached(self, key: str, fn) -> str:
        now = time.time()
        if key in self._cache:
            data, ts = self._cache[key]
            if now - ts < CACHE_TTL:
                logger.info(f"Cache hit: {key}")
                return data
        logger.info(f"Scraping: {key}")
        data = await fn()
        self._cache[key] = (data, now)
        return data

    def invalidate_cache(self):
        self._cache.clear()

    # ── Scrapers ──────────────────────────────────────────────────────────────

    async def _scrape_dashboard(self) -> str:
        return await self._fetch_page_text(self.base_url, wait_selector=".challenge-info, h1, .latest-results")

    async def _scrape_standings(self) -> str:
        url = f"{self.base_url}/stage/68e281fe596fc07e0ed63880"
        return await self._fetch_page_text(url, wait_selector="table, .standings, .group-table")

    async def _scrape_statistics(self) -> str:
        url = f"{self.base_url}/statistics"
        return await self._fetch_page_text(url, wait_selector=".statistics, .stat-row, table")

    async def _scrape_competitors(self) -> str:
        url = f"{self.base_url}/competitors"
        return await self._fetch_page_text(url, wait_selector=".competitor, .team-card, table")

    # ── Playwright helper ─────────────────────────────────────────────────────

    async def _fetch_page_text(self, url: str, wait_selector: str = "body", timeout: int = 20000) -> str:
        """Launch headless browser, wait for JS to render, return visible text."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page: Page = await browser.new_page()

            # Block images/fonts/media to speed things up
            await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,mp4,mp3}", lambda r: r.abort())

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                # Wait for meaningful content to appear
                try:
                    await page.wait_for_selector(wait_selector, timeout=10000)
                except Exception:
                    pass  # Proceed anyway — some selectors may not exist on every page
                await page.wait_for_timeout(2000)  # Extra settle time for SPA hydration
                text = await page.evaluate("() => document.body.innerText")
                return text.strip()
            except Exception as e:
                logger.error(f"Scrape failed for {url}: {e}")
                return f"[Error fetching {url}: {e}]"
            finally:
                await browser.close()
