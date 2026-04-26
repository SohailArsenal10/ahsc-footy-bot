"""
Scraper for challenge.place tournament pages.
Uses plain httpx (no browser) since the site serves full HTML via SSR.
Results are cached for CACHE_TTL seconds to avoid hammering the site.
Memory footprint: ~5MB vs ~400MB with Playwright.
"""

import asyncio
import time
import logging
import httpx
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

CACHE_TTL = 300  # 5 minutes

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


class TextExtractor(HTMLParser):
    """Strips HTML tags and returns clean visible text."""
    def __init__(self):
        super().__init__()
        self.text = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ["script", "style", "noscript"]:
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ["script", "style", "noscript"]:
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            stripped = data.strip()
            if stripped:
                self.text.append(stripped)

    def get_text(self):
        return "\n".join(self.text)


class ChallengeScraper:
    def __init__(self, tournament_url: str):
        self.base_url = tournament_url.rstrip("/")
        self._cache: dict[str, tuple[str, float]] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_all_data(self) -> dict:
        """Fetch all tournament data in parallel."""
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

    def invalidate_cache(self):
        self._cache.clear()

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

    # ── Scrapers ──────────────────────────────────────────────────────────────

    async def _scrape_dashboard(self) -> str:
        return await self._fetch_text(self.base_url)

    async def _scrape_standings(self) -> str:
        return await self._fetch_text(f"{self.base_url}/stage/68e281fe596fc07e0ed63880")

    async def _scrape_statistics(self) -> str:
        return await self._fetch_text(f"{self.base_url}/statistics")

    async def _scrape_competitors(self) -> str:
        return await self._fetch_text(f"{self.base_url}/competitors")

    # ── HTTP helper ───────────────────────────────────────────────────────────

    async def _fetch_text(self, url: str) -> str:
        """Fetch a page with plain HTTP and extract visible text."""
        try:
            async with httpx.AsyncClient(
                headers=HEADERS,
                follow_redirects=True,
                timeout=15.0
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                parser = TextExtractor()
                parser.feed(resp.text)
                return parser.get_text()
        except Exception as e:
            logger.error(f"Scrape failed for {url}: {e}")
            return f"[Error fetching {url}: {e}]"
