# WhAppend

Multimodal Intelligence Platform — timestamped event detection, AI chapters, and reasoning for **Videos, Audio, and Images** powered by **BYOK Groq**, **LangChain**, **Neon Postgres**, and a **Telegram Bot**.

## ✨ Features

- 📱 **Phone Number Allowlist Auth**: Only phone numbers explicitly authorized in the database can log in or chat with the Telegram bot.
- 🔐 **Dual Web Login**:
  - **Phone + Bot OTP**: Enter your allowed phone number on the web and receive a 6-digit login code directly via the Telegram bot.
  - **Telegram Login Widget**: One-click cryptographic HMAC login via Telegram.
- 🔑 **Strict Bring Your Own Key (BYOK) — Encrypted at Rest**:
  - Zero server-side Groq API keys (`GROQ_API_KEY` is removed from server fallbacks).
  - Every user configures their own Groq API key via Telegram (`/setkey`) or the Web UI, validated against Groq and encrypted at rest using **Fernet (`AES-128-CBC + HMAC-SHA256`)**.
- ✈️ **Full Telegram Bot (`aiogram 3.x`)**:
  - Verifies your phone number via Telegram's native *"Share Contact"* button (`contact.user_id == from_user.id`).
  - Free-form LLM chat with persistent per-user memory (`/chatmode`, `/clear`).
  - Send **Videos, Audio, Voice Notes, or Photos** directly in Telegram for multimodal analysis and follow-up Q&A.
  - Query media uploaded from either the Web or Telegram (`/videos`).
  - Admin commands inside Telegram (`/admin_add`, `/admin_remove`, `/admin_list`).
- 🗄️ **Database Architecture (Neon Postgres + JSONB)**:
  - Relational tables (`users`, `api_credentials`, `media`, `chat_messages`, `login_codes`) with **Postgres `JSONB`** columns for document-shaped timeline events and AI chapters (with automatic local SQLite fallback when `DATABASE_URL` is empty).

## 🚀 Quick Start

### 1. Backend & Telegram Bot Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt
cp .env.example .env
```

1. **Generate encryption & JWT secrets**:
   ```bash
   python cli.py generate-secrets
   ```
   Copy `APP_ENCRYPTION_KEY`, `JWT_SECRET`, and `TELEGRAM_WEBHOOK_SECRET` into `backend/.env`.
2. **Database**:
   - Paste your free **Neon Postgres** connection string into `DATABASE_URL=` in `backend/.env` (or leave it empty to use a local SQLite database at `storage/whappend.db`).
3. **Allowlist your phone number**:
   ```bash
   python cli.py add-user +5511999999999 --admin --name "Your Name"
   ```
   *(Or set `ADMIN_PHONES=+5511999999999` in `backend/.env`.)*
4. **Telegram Bot Token**:
   - Message `@BotFather` on Telegram → `/newbot` → copy the token into `TELEGRAM_BOT_TOKEN=` in `backend/.env`.
   - Leave `TELEGRAM_WEBHOOK_URL` empty during local development to run in **long-polling** mode automatically.
5. **Start the server**:
   ```bash
   uvicorn main:app --reload --port 8000
   ```

### 2. Using the Telegram Bot

1. Open your bot in Telegram and send `/start`.
2. Tap **"📱 Share my phone number to verify"** — the bot verifies your number against the allowlist and links your `telegram_user_id`.
3. Send `/setkey` and paste your Groq API key (`gsk_...`). The bot validates it with Groq, encrypts it in the database, and **deletes your message containing the plaintext key**.
4. Send any text message to chat, send a video/voice note/photo to analyze, or send `/videos` to query media uploaded on the Web!

### 3. Frontend

```bash
cd frontend
npm install
npm run dev                       # http://localhost:3000
```
