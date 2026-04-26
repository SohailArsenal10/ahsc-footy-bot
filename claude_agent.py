"""
Claude AI agent.
Fetches tournament data from the scraper and uses Claude to answer
natural-language questions about the AHSC Weekly Footy League.
"""

import os
import logging
import httpx
from challenge_scraper import ChallengeScraper

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """You are FootyBot 🤖⚽ — the official AI assistant for the AHSC Weekly Footy League.

You have access to live tournament data scraped from the team's challenge.place page.
Your job is to answer questions from players and fans in a fun, friendly, and concise way.

Guidelines:
- Keep replies under 300 characters when possible (WhatsApp-friendly)
- Use emojis sparingly but effectively (⚽ 🏆 📊 🥅 🔴)
- If you can't find specific info in the data, say so honestly
- For standings questions, always show position, team name, points
- For top scorers, show name, team, and goals
- Never make up statistics — only use what's in the tournament data
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
        """Main entry point — scrape data, ask Claude, return reply."""
        try:
            # Fetch all tournament data
            data = await self.scraper.get_all_data()
            context = self._format_context(data)

            # Build Claude prompt
            user_message = f"""Here is the latest tournament data:

{context}

---
User question: {user_question}

Answer the question based only on the tournament data above. Keep it concise and WhatsApp-friendly."""

            reply = await self._call_claude(user_message)
            return reply

        except Exception as e:
            logger.error(f"Agent error: {e}")
            return "⚠️ Sorry, I couldn't fetch the latest tournament data right now. Try again in a moment!"

    def _format_context(self, data: dict) -> str:
        sections = []
        for section, content in data.items():
            if content and not content.startswith("[Error"):
                sections.append(f"=== {section.upper()} ===\n{content[:3000]}")  # cap per section
        return "\n\n".join(sections)

    async def _call_claude(self, user_message: str) -> str:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": MODEL,
            "max_tokens": 1024,
            "system": SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": user_message}
            ],
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(ANTHROPIC_API_URL, json=payload, headers=headers)
            resp.raise_for_status()
            result = resp.json()
            return result["content"][0]["text"].strip()
