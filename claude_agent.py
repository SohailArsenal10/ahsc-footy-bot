"""
Claude AI agent.
Fetches tournament data from the scraper and uses Claude to answer
natural-language questions about the AHSC Weekly Footy League.

Uses Anthropic prompt caching to reduce cost and latency on repeated queries.
"""

import os
import logging
import httpx
from challenge_scraper import ChallengeScraper

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"  # Fastest + cheapest, perfect for a WhatsApp bot

# Max characters per scraped section and total context
MAX_CHARS_PER_SECTION = 1500
MAX_TOTAL_CHARS = 5000

SYSTEM_PROMPT = """You are FootyBot - the official AI assistant for the AHSC Weekly Footy League.

You have access to live tournament data scraped from the team's challenge.place page.
Your job is to answer questions from players and fans in a fun, friendly, and concise way.

Guidelines:
- Keep replies under 300 characters when possible (WhatsApp-friendly)
- Use emojis sparingly but effectively
- If you can't find specific info in the data, say so honestly
- For standings questions, always show position, team name, points
- For top scorers, show name, team, and goals
- Never make up statistics - only use what's in the tournament data
- If the user greets you, respond warmly and tell them what you can help with
- Respond in the same language the user writes in

Tournament: AHSC Weekly Footy League
Teams: EPCD, AHSC, BOCA Seniors
"""


class ClaudeAgent:
    def __init__(self, scraper: ChallengeScraper):
        self.scraper = scraper
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    async def answer(self, user_question: str) -> str:
        """Main entry point - scrape data, ask Claude, return reply."""
        try:
            data = await self.scraper.get_all_data()
            context = self._format_context(data)
            reply = await self._call_claude(context, user_question)
            return reply

        except Exception as e:
            logger.error(f"Agent error: {e}")
            return "Sorry, I couldn't fetch the latest tournament data right now. Try again in a moment!"

    def _format_context(self, data: dict) -> str:
        sections = []
        total = 0
        for section, content in data.items():
            if not content or content.startswith("[Error"):
                continue
            trimmed = content[:MAX_CHARS_PER_SECTION]
            if total + len(trimmed) > MAX_TOTAL_CHARS:
                trimmed = trimmed[:MAX_TOTAL_CHARS - total]
                sections.append(f"=== {section.upper()} ===\n{trimmed}")
                break
            sections.append(f"=== {section.upper()} ===\n{trimmed}")
            total += len(trimmed)
        return "\n\n".join(sections)

    async def _call_claude(self, context: str, user_question: str) -> str:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "prompt-caching-2024-07-31",  # Enable prompt caching
            "content-type": "application/json",
        }

        # The system prompt + tournament context is marked for caching.
        # Anthropic caches this block for 5 minutes — any question asked within
        # that window reuses the cached version, saving ~90% on those tokens.
        payload = {
            "model": MODEL,
            "max_tokens": 512,
            "system": [
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                },
                {
                    "type": "text",
                    "text": f"Here is the latest tournament data:\n\n{context}",
                    "cache_control": {"type": "ephemeral"},  # Cache this block
                }
            ],
            "messages": [
                {
                    "role": "user",
                    "content": f"{user_question}\n\nAnswer based only on the tournament data above. Keep it concise and WhatsApp-friendly."
                }
            ],
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(ANTHROPIC_API_URL, json=payload, headers=headers)
            if not resp.is_success:
                logger.error(f"Claude API error {resp.status_code}: {resp.text}")
            resp.raise_for_status()
            result = resp.json()

            # Log cache performance
            usage = result.get("usage", {})
            cache_read = usage.get("cache_read_input_tokens", 0)
            cache_created = usage.get("cache_creation_input_tokens", 0)
            if cache_read:
                logger.info(f"Cache HIT - saved {cache_read} tokens")
            elif cache_created:
                logger.info(f"Cache CREATED - {cache_created} tokens cached for next requests")

            return result["content"][0]["text"].strip()
