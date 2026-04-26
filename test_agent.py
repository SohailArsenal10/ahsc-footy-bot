"""
Test the Claude agent with sample questions.
Usage: ANTHROPIC_API_KEY=xxx python tests/test_agent.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from challenge_scraper import ChallengeScraper
from claude_agent import ClaudeAgent


SAMPLE_QUESTIONS = [
    "Hi! What can you help me with?",
    "Who's top of the table?",
    "What were the latest match results?",
    "Who is the top scorer?",
    "When is the next match?",
    "How is BOCA Seniors doing this season?",
]


async def main():
    scraper = ChallengeScraper("https://challenge.place/c/68e25e0e0cd837a479b79cc6")
    agent = ClaudeAgent(scraper=scraper)

    for question in SAMPLE_QUESTIONS:
        print(f"\n👤 User: {question}")
        answer = await agent.answer(question)
        print(f"🤖 Bot:  {answer}")
        print("-" * 60)


if __name__ == "__main__":
    asyncio.run(main())
