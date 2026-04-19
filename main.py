"""
AHSC Weekly Footy League - WhatsApp AI Bot
FastAPI webhook server using Twilio WhatsApp Sandbox
(Drop-in replacement for the Meta Cloud API version)
"""

import os
import logging
from fastapi import FastAPI, Request, Response, Form
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv
from twilio.rest import Client
from twilio.request_validator import RequestValidator

from bot.claude_agent import ClaudeAgent
from scraper.challenge_scraper import ChallengeScraper

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AHSC Footy Bot — Twilio")

# Initialise shared instances
scraper = ChallengeScraper(
    tournament_url=os.getenv("TOURNAMENT_URL", "https://challenge.place/c/68e25e0e0cd837a479b79cc6")
)
agent = ClaudeAgent(scraper=scraper)

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")  # Twilio sandbox number

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


# ── Incoming WhatsApp messages from Twilio ────────────────────────────────────
@app.post("/webhook")
async def receive_message(
    request: Request,
    From: str = Form(...),       # sender's WhatsApp number  e.g. whatsapp:+919876543210
    Body: str = Form(...),       # message text
    NumMedia: str = Form("0"),   # number of media attachments
):
    logger.info(f"Message from {From}: {Body}")

    # Ignore empty messages or media-only messages
    if not Body.strip():
        return PlainTextResponse("", status_code=200)

    try:
        reply = await agent.answer(Body.strip())
    except Exception as e:
        logger.error(f"Agent error: {e}")
        reply = "⚠️ Sorry, couldn't fetch tournament data right now. Try again in a moment!"

    # Send reply via Twilio
    twilio_client.messages.create(
        from_=TWILIO_WHATSAPP_FROM,
        to=From,
        body=reply,
    )

    # Twilio expects a 200 with empty TwiML or plain text
    return PlainTextResponse("", status_code=200)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "bot": "AHSC Footy Bot 🏆", "provider": "Twilio"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
