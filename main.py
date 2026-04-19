"""
AHSC Weekly Footy League - WhatsApp AI Bot
FastAPI webhook server that integrates WhatsApp Cloud API + Claude AI + challenge.place scraper
"""

import os
import logging
import httpx
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from bot.claude_agent import ClaudeAgent
from scraper.challenge_scraper import ChallengeScraper

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AHSC Footy Bot")

# Initialise shared instances
scraper = ChallengeScraper(tournament_url=os.getenv("TOURNAMENT_URL", "https://challenge.place/c/68e25e0e0cd837a479b79cc6"))
agent = ClaudeAgent(scraper=scraper)

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "ahsc_footy_bot_2025")


# ── Webhook verification (Meta requires this on first setup) ──────────────────
@app.get("/webhook")
async def verify_webhook(request: Request):
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("Webhook verified ✅")
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


# ── Incoming WhatsApp messages ────────────────────────────────────────────────
@app.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()
    logger.info(f"Incoming payload: {body}")

    try:
        entry = body["entry"][0]["changes"][0]["value"]

        # Ignore status updates (delivered/read receipts)
        if "statuses" in entry:
            return Response(status_code=200)

        message = entry["messages"][0]
        from_number = message["from"]
        msg_type = message.get("type")

        if msg_type == "text":
            user_text = message["text"]["body"]
        elif msg_type == "interactive":
            # Handle button replies
            user_text = message["interactive"]["button_reply"]["title"]
        else:
            await send_whatsapp_message(from_number, "Sorry, I can only handle text messages right now ⚽")
            return Response(status_code=200)

        logger.info(f"Message from {from_number}: {user_text}")

        # Send typing indicator
        await send_typing_indicator(entry.get("metadata", {}).get("phone_number_id", WHATSAPP_PHONE_ID), message["id"])

        # Get AI response
        reply = await agent.answer(user_text)
        await send_whatsapp_message(from_number, reply)

    except (KeyError, IndexError) as e:
        logger.warning(f"Could not parse message: {e}")

    return Response(status_code=200)


# ── WhatsApp API helpers ──────────────────────────────────────────────────────
async def send_whatsapp_message(to: str, text: str):
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
            logger.error(f"WhatsApp send failed: {resp.text}")


async def send_typing_indicator(phone_number_id: str, message_id: str):
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
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


# ── Health check ─────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "bot": "AHSC Footy Bot 🏆"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
