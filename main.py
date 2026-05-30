"""
AHSC Weekly Footy League - WhatsApp AI Bot
FastAPI webhook server using Meta WhatsApp Cloud API

Supports:
- Direct (1-to-1) messages     → always responds
- Group messages                → only responds when bot is mentioned
                                  e.g. "@footybot who's top of the table?"
"""

import os
import logging
import re
import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from claude_agent import ClaudeAgent
from challenge_scraper import ChallengeScraper

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AHSC Footy Bot — WhatsApp Cloud API")

# ── Config ────────────────────────────────────────────────────────────────────

# The trigger keyword(s) the bot listens for in group chats.
# Case-insensitive. Add aliases e.g. "@footybot,@footy,@bot"
BOT_TRIGGERS = [t.lower() for t in os.getenv("BOT_TRIGGERS", "@footybot").split(",")]

WHATSAPP_TOKEN    = os.getenv("WHATSAPP_TOKEN")        # Meta permanent/temp access token
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")     # Meta Phone Number ID
VERIFY_TOKEN      = os.getenv("VERIFY_TOKEN", "ahsc_footy_bot_2025")

# ── Shared instances ──────────────────────────────────────────────────────────
scraper = ChallengeScraper(
    tournament_url=os.getenv("TOURNAMENT_URL", "https://challenge.place/c/68e25e0e0cd837a479b79cc6")
)
agent = ClaudeAgent(scraper=scraper)


# ── Webhook verification (one-time, Meta requires this on setup) ──────────────

@app.get("/webhook")
async def verify_webhook(request: Request):
    params   = dict(request.query_params)
    mode     = params.get("hub.mode")
    token    = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("Webhook verified ✅")
        return PlainTextResponse(challenge)

    logger.warning("Webhook verification failed ❌")
    return Response(status_code=403)


# ── Incoming WhatsApp messages ────────────────────────────────────────────────

@app.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()
    # Log only metadata, never log the full payload (contains sensitive data)
    logger.debug(f"Incoming webhook payload received")

    try:
        entry  = body["entry"][0]["changes"][0]["value"]

        # Ignore delivery/read status updates
        if "statuses" in entry:
            return Response(status_code=200)

        message      = entry["messages"][0]
        from_number  = message["from"]          # sender's phone number
        msg_type     = message.get("type")
        contacts     = entry.get("contacts", [{}])
        sender_name  = contacts[0].get("profile", {}).get("name", "Player")

        # Extract group ID if present (group messages only)
        group_id = message.get("context", {}).get("group_id") or \
                   entry.get("metadata", {}).get("group_id", "")

        # ── Extract message text ──────────────────────────────────────────────
        if msg_type == "text":
            body_text = message["text"]["body"].strip()
        elif msg_type == "interactive":
            body_text = message["interactive"]["button_reply"]["title"].strip()
        else:
            # Media / unsupported type — ignore silently
            return Response(status_code=200)

        is_group = bool(group_id)
        logger.info(f"{'[GROUP]' if is_group else '[DM]'} {from_number} ({sender_name}): {body_text!r}")

        # ── Group logic: only respond when mentioned ──────────────────────────
        if is_group:
            trigger_used = _find_trigger(body_text)
            if not trigger_used:
                logger.info("Group message — bot not mentioned, ignoring.")
                return Response(status_code=200)

            question = _strip_trigger(body_text, trigger_used).strip()
            if not question:
                question = "Give me a quick tournament summary"

            reply_to = group_id
            prefix   = f"_{sender_name} asked:_\n"

        # ── DM logic: always respond ──────────────────────────────────────────
        else:
            question = body_text
            reply_to = from_number
            prefix   = ""

        # ── Refresh command — clears scraper cache ────────────────────────────
        if body_text.lower().strip() in ["refresh", "@footybot refresh"]:
            scraper.invalidate_cache()
            await _send_message(reply_to, "Cache cleared! Next query will fetch fresh data from challenge.place ✅")
            return Response(status_code=200)

        # ── Mark message as read (shows blue ticks) ───────────────────────────
        await _mark_read(message["id"])

        # ── Get AI answer ─────────────────────────────────────────────────────
        try:
            answer = await agent.answer(question)
        except Exception as e:
            logger.error(f"Agent error: {e}")
            answer = "⚠️ Couldn't fetch tournament data right now. Try again in a moment!"

        await _send_message(reply_to, f"{prefix}{answer}")

    except (KeyError, IndexError) as e:
        logger.warning(f"Could not parse payload: {e}")

    return Response(status_code=200)


# ── WhatsApp Cloud API helpers ────────────────────────────────────────────────

async def _send_message(to: str, text: str):
    """Send a text message via WhatsApp Cloud API."""
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            logger.error(f"Send failed: {resp.text}")


async def _mark_read(message_id: str):
    """Mark an incoming message as read (blue ticks)."""
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload, headers=headers)


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
        "provider": "WhatsApp Cloud API",
        "triggers": BOT_TRIGGERS,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
