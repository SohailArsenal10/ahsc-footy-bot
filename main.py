"""
AHSC Weekly Footy League - WhatsApp AI Bot
FastAPI webhook server using Twilio WhatsApp Sandbox

Supports:
- Direct (1-to-1) messages     → always responds
- Group messages                → only responds when bot is mentioned
                                  e.g. "@footybot who's top of the table?"
"""

import os
import logging
import re
from fastapi import FastAPI, Request, Form
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv
from twilio.rest import Client

from bot.claude_agent import ClaudeAgent
from scraper.challenge_scraper import ChallengeScraper

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AHSC Footy Bot — Twilio")

# ── Config ────────────────────────────────────────────────────────────────────

# The trigger keyword(s) the bot listens for in group chats.
# Case-insensitive. Add aliases if you want e.g. ["@footybot", "@footy", "@bot"]
BOT_TRIGGERS = [t.lower() for t in os.getenv("BOT_TRIGGERS", "@footybot").split(",")]

TWILIO_ACCOUNT_SID   = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN    = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# ── Shared instances ──────────────────────────────────────────────────────────
scraper = ChallengeScraper(
    tournament_url=os.getenv("TOURNAMENT_URL", "https://challenge.place/c/68e25e0e0cd837a479b79cc6")
)
agent = ClaudeAgent(scraper=scraper)


# ── Webhook ───────────────────────────────────────────────────────────────────

@app.post("/webhook")
async def receive_message(
    request: Request,
    From: str        = Form(...),   # sender  e.g. whatsapp:+60123456789
    To: str          = Form(...),   # bot number
    Body: str        = Form(""),    # message text
    NumMedia: str    = Form("0"),
    WaGroupId: str   = Form(""),    # non-empty when message is from a group
    ProfileName: str = Form(""),    # sender's WhatsApp display name
):
    body_text   = Body.strip()
    is_group    = bool(WaGroupId)
    sender_name = ProfileName or "Player"

    logger.info(f"{'[GROUP]' if is_group else '[DM]'} {From} → {body_text!r}")

    # ── Ignore empty / media-only messages ───────────────────────────────────
    if not body_text:
        return PlainTextResponse("", status_code=200)

    # ── Group message logic ───────────────────────────────────────────────────
    if is_group:
        trigger_used = _find_trigger(body_text)
        if not trigger_used:
            # Bot not mentioned — stay silent
            logger.info("Group message — bot not mentioned, ignoring.")
            return PlainTextResponse("", status_code=200)

        # Strip the trigger keyword from the question before sending to Claude
        question = _strip_trigger(body_text, trigger_used).strip()
        if not question:
            # Someone just typed "@footybot" with nothing after it
            question = "Give me a quick tournament summary"

        reply_to = f"whatsapp:{WaGroupId}"   # reply to the group
        # Prefix reply with sender's name so the group knows who triggered it
        prefix = f"_{sender_name} asked:_\n"

    # ── Direct message logic ──────────────────────────────────────────────────
    else:
        question = body_text
        reply_to = From
        prefix   = ""

    logger.info(f"Question: {question!r} → replying to {reply_to}")

    # ── Get AI answer ─────────────────────────────────────────────────────────
    try:
        answer = await agent.answer(question)
    except Exception as e:
        logger.error(f"Agent error: {e}")
        answer = "⚠️ Couldn't fetch tournament data right now. Try again in a moment!"

    reply = f"{prefix}{answer}"

    # ── Send reply ────────────────────────────────────────────────────────────
    twilio_client.messages.create(
        from_=TWILIO_WHATSAPP_FROM,
        to=reply_to,
        body=reply,
    )

    return PlainTextResponse("", status_code=200)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_trigger(text: str) -> str | None:
    """Return the trigger keyword found in text, or None."""
    lower = text.lower()
    for trigger in BOT_TRIGGERS:
        if trigger in lower:
            return trigger
    return None


def _strip_trigger(text: str, trigger: str) -> str:
    """Remove the trigger keyword from the message (case-insensitive)."""
    return re.sub(re.escape(trigger), "", text, flags=re.IGNORECASE).strip()


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "bot": "AHSC Footy Bot 🏆",
        "provider": "Twilio",
        "triggers": BOT_TRIGGERS,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
