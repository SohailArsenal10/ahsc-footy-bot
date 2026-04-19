"""
Quick smoke test — run locally before deploying.
Usage: python tests/test_scraper.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scraper.challenge_scraper import ChallengeScraper


async def main():
    scraper = ChallengeScraper("https://challenge.place/c/68e25e0e0cd837a479b79cc6")
    print("🔍 Scraping tournament data...\n")

    data = await scraper.get_all_data()

    for section, content in data.items():
        print(f"{'='*50}")
        print(f"📌 {section.upper()}")
        print(f"{'='*50}")
        print(content[:1000])
        print()


if __name__ == "__main__":
    asyncio.run(main())
