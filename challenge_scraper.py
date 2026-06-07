"""
Scraper for challenge.place tournament pages.
Uses httpx for most pages (lightweight), Steel.dev cloud browser for player statistics
(which requires clicking the PLAYER tab to load dynamic content).
"""

import asyncio
import time
import logging
import httpx
import os
from html.parser import HTMLParser
from playwright.async_api import async_playwright
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

# Steel.dev cloud browser connection
STEEL_API_KEY = os.getenv("STEEL_API_KEY", "")

# Cache for 1 hour — fresh enough for a weekly league,
# and avoids hammering challenge.place on every message.
# Force a refresh anytime by messaging "@footybot refresh"
CACHE_TTL = 604800  # 7 days in seconds

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


def _clean_content(text: str) -> str:
    """Remove header, navigation, schedule, and footer noise from scraped content."""
    lines = text.split('\n')
    cleaned = []
    skip_until = None
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Skip header/navigation
        if any(nav in stripped for nav in ['Sign in', 'AHSC Weekly Footy League', 'Dashboard', 'Stages', 'Competitors', 'Statistics', 'News']):
            continue
        
        # Skip schedule section
        if 'Schedule' in stripped or 'Week' in stripped:
            skip_until = 'Try Challenge'
            continue
        
        # Skip footer section and residual noise
        if any(footer in stripped for footer in ['Try Challenge Place app', 'Community', 'FAQ', 'Blog', 'Modalities', 'Resources', 'Privacy policy', 'Terms of service', 'Go Premium', 'Contact us', 'Report a problem', 'Your feedback', 'Challenge yourself', 'Create challenge', 'Quick try', 'Discover more', 'A complete multiplatform', 'Do like millions', 'More', 'Minimize']):
            skip_until = None
            continue
        
        # Skip if we're in a section to skip
        if skip_until and skip_until in stripped:
            skip_until = None
            continue
        
        if skip_until:
            continue
        
        # Skip single dots and other noise
        if stripped in ['.', '']:
            continue
        
        # Only add non-empty lines
        if stripped:
            cleaned.append(stripped)
    
    return "\n".join(cleaned)


class ChallengeScraper:
    def __init__(self, tournament_url: str):
        self.base_url = tournament_url.rstrip("/")
        self._cache: dict[str, tuple[str, float]] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_all_data(self) -> dict:
        """Fetch all tournament data in parallel."""
        standings, team_stats, player_stats, competitors = await asyncio.gather(
            self._cached("standings", self._scrape_standings),
            self._cached("team_statistics", self._scrape_team_statistics),
            self._cached("player_statistics", self._scrape_player_statistics),
            self._cached("competitors", self._scrape_competitors),
        )
        return {
            "standings": standings,
            "team_statistics": team_stats,
            "player_statistics": player_stats,
            "competitors": competitors,
        }

    def invalidate_cache(self):
        """Force a fresh scrape on next request. Triggered by '@footybot refresh'."""
        self._cache.clear()
        logger.info("Cache cleared - next request will scrape fresh data")

    def cache_age_minutes(self) -> int:
        """Returns age of oldest cache entry in minutes, or -1 if empty."""
        if not self._cache:
            return -1
        oldest = min(ts for _, ts in self._cache.values())
        return int((time.time() - oldest) / 60)

    # ── Cache wrapper ─────────────────────────────────────────────────────────

    async def _cached(self, key: str, fn) -> str:
        now = time.time()
        if key in self._cache:
            data, ts = self._cache[key]
            if now - ts < CACHE_TTL:
                logger.info(f"Cache hit: {key} (age: {int((now-ts)/60)}min)")
                return data
        logger.info(f"Scraping fresh: {key}")
        data = await fn()
        self._cache[key] = (data, now)
        return data

    # ── Scrapers ──────────────────────────────────────────────────────────────

    async def _scrape_standings(self) -> str:
        text = await self._fetch_text(f"{self.base_url}/stage/68e281fe596fc07e0ed63880")
        return _clean_content(text)

    async def _scrape_team_statistics(self) -> str:
        """Scrape team-level statistics from statistics page."""
        text = await self._fetch_text(f"{self.base_url}/statistics")
        return _clean_content(text)

    async def _scrape_player_statistics(self) -> str:
        """Scrape player-level statistics from statistics page using Steel.dev cloud browser.
        
        The PLAYER tab is loaded dynamically via JavaScript, so we use Steel.dev's
        remote browser to:
        1. Load the statistics page
        2. Click the PLAYER tab button
        3. Wait for player data to load
        4. Extract the player statistics
        """
        if not STEEL_API_KEY:
            logger.warning("STEEL_API_KEY not set, skipping player statistics")
            return "[Player statistics unavailable - STEEL_API_KEY not configured]"
        
        try:
            # Connect to Steel.dev cloud browser via CDP
            steel_url = f"wss://connect.steel.dev?apiKey={STEEL_API_KEY}"
            
            async with async_playwright() as p:
                browser = await p.chromium.connect_over_cdp(steel_url)
                page = await browser.new_page()
                
                try:
                    # Load statistics page
                    await page.goto(f"{self.base_url}/statistics", wait_until="domcontentloaded", timeout=15000)
                    
                    # Wait a bit for initial render
                    await page.wait_for_timeout(2000)
                    
                    # Click PLAYER tab button
                    player_tab = page.locator("text=Player").first
                    await player_tab.click()
                    
                    # Wait for player data to load
                    await page.wait_for_selector("text=Top scorers", timeout=10000)
                    
                    # Wait a bit for data to fully render
                    await page.wait_for_timeout(1000)
                    
                    # Click all "See all" buttons to expand all player lists
                    max_attempts = 15
                    for attempt in range(max_attempts):
                        see_all_buttons = page.locator("text=See all")
                        count = await see_all_buttons.count()
                        if count == 0:
                            break
                        try:
                            button = see_all_buttons.first
                            await button.click(timeout=5000)
                            await page.wait_for_timeout(1500)
                        except Exception as e:
                            logger.debug(f"Could not click See all button: {e}")
                            break
                    
                    # Final wait to ensure all content is rendered
                    await page.wait_for_timeout(2000)
                    
                    # Extract all text content
                    content = await page.content()
                    parser = TextExtractor()
                    parser.feed(content)
                    full_text = parser.get_text()
                    
                    # Extract and clean player stats section
                    player_stats = self._extract_player_stats(full_text)
                    return _clean_content(player_stats)
                    
                finally:
                    await browser.close()
                    
        except Exception as e:
            logger.error(f"Steel.dev scrape failed for player statistics: {e}")
            return f"[Error scraping player statistics: {e}]"

    async def _scrape_competitors(self) -> str:
        text = await self._fetch_text(f"{self.base_url}/competitors")
        return _clean_content(text)

    # ── HTTP helper ───────────────────────────────────────────────────────────

    async def _fetch_text(self, url: str) -> str:
        """Fetch a page with plain HTTP and extract visible text."""
        try:
            async with httpx.AsyncClient(
                headers=HEADERS,
                follow_redirects=True,
                timeout=15.0,
                verify=False  # ⚠️ Disable SSL verification for local testing
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                parser = TextExtractor()
                parser.feed(resp.text)
                return parser.get_text()
        except Exception as e:
            logger.error(f"Scrape failed for {url}: {e}")
            return f"[Error fetching {url}: {e}]"

    async def _fetch_html(self, url: str) -> str:
        """Fetch raw HTML from a URL."""
        try:
            async with httpx.AsyncClient(
                headers=HEADERS,
                follow_redirects=True,
                timeout=15.0,
                verify=False
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.text
        except Exception as e:
            logger.error(f"HTML fetch failed for {url}: {e}")
            return ""

    def _extract_player_stats(self, full_text: str) -> str:
        """Extract player-level statistics from full text.
        
        Looks for the PLAYER tab section which contains individual player stats
        (Top scorers, Assists, Red cards, Yellow cards, Penalty goals, Own goals, Dead ball goals).
        """
        if not full_text:
            return "[Error: No content]"
        
        lines = full_text.split('\n')
        
        # Find where player stats start (look for "Top scorers" which is first in PLAYER section)
        # We need to skip the TEAM section which also has "Top scorers"
        player_start = -1
        
        # Player names that only appear in PLAYER tab
        player_indicators = ['Vatsa', 'Azeem', 'Basher', 'Abhay', 'Lokin', 'Sohail', 'Milind', 'Anirudh', 'Manideep', 'Arjun']
        
        for i, line in enumerate(lines):
            if any(name in line for name in player_indicators):
                player_start = i
                break
        
        if player_start == -1:
            return "[No player statistics found]"
        
        # Extract from this point until footer
        # Look for all player stat categories: Top scorers, Own goals, Assists, Yellow cards, Red cards, Penalty goals, Dead ball situation goals
        player_lines = []
        for i in range(player_start, len(lines)):
            line = lines[i].strip()
            if not line:
                continue
            # Stop at footer (more specific patterns)
            if any(skip in line for skip in ['Try Challenge Place app', 'Discover more', 'Statistics\nSoccer']):
                break
            player_lines.append(line)
        
        return "\n".join(player_lines) if player_lines else "[No player statistics found]"
