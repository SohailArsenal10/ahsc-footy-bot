"""
Quick smoke test — run locally before deploying.
Usage: python test_scraper.py
"""
import asyncio
from challenge_scraper import ChallengeScraper

# Match the limits from claude_agent.py
MAX_CHARS_PER_SECTION = 3000
MAX_TOTAL_CHARS = 5000


async def main():
    scraper = ChallengeScraper("https://challenge.place/c/68e25e0e0cd837a479b79cc6")
    print("🔍 Scraping tournament data...\n")

    data = await scraper.get_all_data()

    total_chars = 0
    for section, content in data.items():
        print(f"{'='*50}")
        print(f"📌 {section.upper()} ({len(content)} chars)")
        print(f"{'='*50}")
        trimmed = content[:MAX_CHARS_PER_SECTION]
        print(trimmed)
        print()
        total_chars += len(trimmed)
        if total_chars >= MAX_TOTAL_CHARS:
            break
    
    print(f"\n{'='*50}")
    print("📋 FULL DATA SIZES (before trimming):")
    print(f"{'='*50}")
    for section, content in data.items():
        print(f"{section}: {len(content)} chars")

    print(f"{'='*50}")
    print(f"📊 Total characters sent to Claude: {total_chars}")
    print(f"📊 Estimated tokens: ~{total_chars // 4}")
    print(f"{'='*50}")
    if total_chars < 1024:
        print("⚠️  WARNING: Context is below 1024 tokens - prompt caching will NOT work!")
    else:
        print("✅ Context is above 1024 tokens - prompt caching should work")


if __name__ == "__main__":
    asyncio.run(main())
