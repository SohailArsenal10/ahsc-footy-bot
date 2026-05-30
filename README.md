# ⚽ AHSC Weekly Footy League — WhatsApp AI Bot

A WhatsApp bot that answers natural-language questions about your soccer tournament by scraping live data from challenge.place and powering responses with Claude AI.

---

## 🏗️ Architecture

```
WhatsApp User
     ↓  (sends message)
Meta WhatsApp Cloud API
     ↓  (POST to your webhook)
FastAPI Server  (main.py)
     ↓
ChallengeScraper  →  challenge.place  (HTTP/httpx)
     ↓
ClaudeAgent  →  Anthropic API  (claude-haiku)
     ↓
Reply sent back via WhatsApp Cloud API
```

---

## 📁 Project Structure

```
whatsapp-soccer-bot/
├── main.py                    # FastAPI webhook server
├── challenge_scraper.py       # HTTP scraper for challenge.place
├── claude_agent.py            # Claude AI agent
├── test_scraper.py            # Test scraping locally
├── test_agent.py              # Test Claude Q&A locally
├── requirements.txt
├── render.yaml                # One-click Render deployment
└── .env.example               # Environment variables template
```

---

## 🚀 Setup Guide

### Step 1 — Clone & install dependencies

```bash
git clone <your-repo>
cd whatsapp-soccer-bot
pip install -r requirements.txt
```

### Step 2 — Get your API keys

#### Anthropic API Key (Claude)
1. Go to https://console.anthropic.com
2. Sign up → API Keys → Create Key
3. You get $5 free credit (enough for thousands of bot replies)

#### WhatsApp Cloud API (Meta) — Free
1. Go to https://developers.facebook.com
2. Create an App → choose **Business** type
3. Add the **WhatsApp** product
4. Go to **WhatsApp → API Setup**
5. Note down:
   - **Phone Number ID** → `WHATSAPP_PHONE_ID`
   - **Temporary Access Token** (or generate a permanent one) → `WHATSAPP_TOKEN`

### Step 3 — Configure environment

```bash
cp .env.example .env
# Edit .env and fill in your keys
```

```env
ANTHROPIC_API_KEY=sk-ant-...
WHATSAPP_TOKEN=EAAxxxxx...
WHATSAPP_PHONE_ID=1234567890
VERIFY_TOKEN=ahsc_footy_bot_2025
TOURNAMENT_URL=https://challenge.place/c/68e25e0e0cd837a479b79cc6
```

### Step 4 — Test locally

```bash
# Test the scraper
python test_scraper.py

# Test the AI agent (requires ANTHROPIC_API_KEY)
python test_agent.py

# Run the server locally
uvicorn main:app --reload --port 8000
```

### Step 5 — Deploy to Render (free)

1. Push your code to a GitHub repo
2. Go to https://render.com → New → Web Service
3. Connect your GitHub repo
4. Render auto-detects `render.yaml`
5. Add your secret env vars in the Render dashboard:
   - `ANTHROPIC_API_KEY`
   - `WHATSAPP_TOKEN`
   - `WHATSAPP_PHONE_ID`
6. Deploy → note your public URL e.g. `https://ahsc-footy-bot.onrender.com`

### Step 6 — Connect WhatsApp Webhook

1. In Meta Developer Console → WhatsApp → Configuration → Webhooks
2. Set **Callback URL**: `https://ahsc-footy-bot.onrender.com/webhook`
3. Set **Verify Token**: `ahsc_footy_bot_2025`
4. Click **Verify and Save**
5. Subscribe to **messages** field

### Step 7 — Add your WhatsApp number

In Meta console → WhatsApp → API Setup:
- Add your personal WhatsApp number as a test recipient
- Send a message to the test number shown and your bot will reply!

---

## 💬 Example Conversations

```
You: Who's top of the table?
Bot: 🏆 BOCA Seniors lead with 12pts from 5 games (W4 D0 L1)

You: Latest results?
Bot: 📊 Latest results:
     EPCD 3–1 AHSC
     EPCD 0–4 BOCA
     AHSC 2–2 BOCA

You: Who's the top scorer?
Bot: ⚽ Top scorer: João (BOCA Seniors) with 9 goals this season!

You: How is AHSC doing?
Bot: AHSC are 3rd with 5pts — 1W 2D 2L, GD -2. Come on lads! 💪
```

---

## ⚙️ Configuration Notes

- **Cache TTL**: Scrape results are cached for 7 days (`CACHE_TTL` in `challenge_scraper.py`) - force refresh with "@footybot refresh"
- **Memory footprint**: ~5MB (uses httpx instead of Playwright)
- **Model**: Claude Haiku (fastest + cheapest for WhatsApp bots)
- **WhatsApp free tier**: 1,000 conversations/month free
- **Render free tier**: Spins down after 15min inactivity (first message may be slow — ~30s cold start)
- **To avoid cold starts**: Upgrade to Render Starter ($7/mo) or use Railway/Fly.io

---

## 🛠️ Troubleshooting

| Problem | Fix |
|---|---|
| Scraper returns empty data | The site may be down or blocked — check tournament URL is accessible |
| WhatsApp webhook not verifying | Check `VERIFY_TOKEN` matches exactly in `.env` and Meta console |
| Claude not responding | Check `ANTHROPIC_API_KEY` is valid and has credit |
| Render deploy fails | Ensure all dependencies in requirements.txt are installable |

---

## 📜 License

MIT — free to use and modify for your league!
