# 🛠️ WhAppend — Technical & Developer Setup Guide

This document covers the internal architecture, database schema, authentication flows, encryption design, Telegram bot commands, REST API reference, and production deployment steps for **WhAppend**.

---

## 1. 📂 Repository Structure

```text
whappend/
├── README.md
├── docs/
│   └── TECHNICAL_SETUP.md         # This technical guide
├── backend/
│   ├── main.py                    # FastAPI app, CORS, non-blocking lifespan, Telegram webhook route
│   ├── config.py                  # Pydantic BaseSettings (.env loader)
│   ├── cli.py                     # CLI for allowlist management & cryptographic secret generation
│   ├── store.py                   # User-scoped persistence facade over SQLAlchemy + JSONB
│   ├── requirements.txt           # Memory-optimized Python dependencies (<120 MB RAM on boot)
│   ├── bot/
│   │   └── app.py                 # Aiogram 3.x router, FSM states, media downloader & webhook/polling
│   ├── core/
│   │   ├── security.py            # E.164 normalization, Fernet AES encryption, JWT, OTP & TG HMAC
│   │   ├── repositories.py        # CRUD for Users, ApiCredentials, LoginCodes, and ChatMessages
│   │   └── deps.py                # FastAPI dependencies: get_current_user, get_current_admin, resolve_user_groq_key
│   ├── db/
│   │   ├── base.py                # SQLAlchemy engine (Neon Postgres + psycopg3 or SQLite fallback)
│   │   └── models.py              # ORM models with PostgreSQL JSONB variant columns
│   ├── models/
│   │   └── schemas.py             # Pydantic API request/response contracts
│   ├── routers/
│   │   ├── auth.py                # /auth/otp/request, /auth/otp/verify, /auth/telegram-widget, /auth/me
│   │   ├── keys.py                # /me/groq-key (GET, PUT, DELETE encrypted BYOK key)
│   │   ├── admin.py               # /admin/users (GET, POST, DELETE allowlisted phone numbers)
│   │   ├── videos.py              # /videos (upload, status, events, media stream, AI chapters)
│   │   └── ask.py                 # /ask (Multi-Query RAG & Agent Q&A)
│   └── services/
│       ├── frame_extractor.py     # Lazy-loaded OpenCV interval frame sampler
│       ├── vision_service.py      # 2x2 collage Groq Vision analyzer + single-image OCR/scene analyzer
│       ├── audio_service.py       # FFmpeg 16kHz audio extractor + Groq Whisper API transcription
│       ├── event_merger.py        # Temporal alignment of visual and spoken events
│       ├── rag_service.py         # In-memory Hybrid BM25 + Multi-Query ranker & RAG orchestrator
│       └── langchain_service.py   # LCEL conversational memory, multi-query, structured chapters & tools agent
└── frontend/
    ├── src/
    │   ├── app/
    │   │   ├── page.tsx           # Auth gate, unified Web/Telegram media library, workspace controller
    │   │   └── globals.css        # Custom dark-theme design system
    │   ├── components/
    │   │   ├── AuthModal.tsx      # Dual login UI: Phone + Bot OTP & Telegram Login Widget
    │   │   ├── ApiKeyModal.tsx    # Encrypted BYOK Groq key manager + Admin Allowlist panel
    │   │   ├── VideoUploader.tsx  # Drag-and-drop video/audio/image uploader
    │   │   ├── MediaViewer.tsx    # Synchronized Video, Audio waveform, and Image viewer
    │   │   ├── EventTimeline.tsx  # Timestamped event cards with modality filtering
    │   │   ├── ChaptersView.tsx   # AI-generated structured chapters view
    │   │   └── ChatPanel.tsx      # Multi-turn RAG chat with Agent Mode toggle
    │   └── lib/
    │       ├── api.ts             # Typed fetch client with Bearer JWT injection
    │       ├── types.ts           # TypeScript interfaces matching FastAPI schemas
    │       └── utils.ts           # Timestamp formatting & modality helpers
```

---

## 2. 🗄️ Database Architecture (Neon PostgreSQL + `JSONB`)

WhAppend uses a **hybrid relational + document schema** in PostgreSQL (`db/models.py`).
Instead of running a separate NoSQL cluster alongside PostgreSQL, SQLAlchemy's `JSON().with_variant(JSONB(), "postgresql")` stores relational entities with strict foreign-key constraints while storing variable-length timeline events and AI chapters as binary `JSONB` documents.

```mermaid
erDiagram
  USERS ||--o{ API_CREDENTIALS : "stores encrypted BYOK"
  USERS ||--o{ MEDIA : "owns"
  USERS ||--o{ CHAT_MESSAGES : "converses"
  USERS ||--o{ LOGIN_CODES : "requests OTP"

  USERS {
    string id PK "UUID v4"
    string phone_e164 UK "Normalized E.164 (+5522999185035)"
    bigint telegram_user_id UK "Verified Telegram numeric ID"
    string telegram_username "Optional @handle"
    string display_name "User name"
    string role "'admin' | 'user'"
    boolean is_active "Allowlist toggle"
    string active_media_id "Currently selected media in Telegram"
    datetime created_at
    datetime last_login_at
  }

  API_CREDENTIALS {
    string id PK "UUID v4"
    string user_id FK "ON DELETE CASCADE"
    string provider "'groq'"
    text key_ciphertext "Fernet AES-128-CBC + HMAC token"
    string key_last4 "Last 4 chars (e.g. 'tjYL')"
    datetime validated_at
    datetime updated_at
  }

  MEDIA {
    string id PK "UUID v4"
    string user_id FK "ON DELETE CASCADE"
    string filename "Disk filename"
    string original_name "Original upload name"
    string media_type "'video' | 'audio' | 'image'"
    string status "'pending' | 'processing' | 'completed' | 'failed'"
    string source "'web' | 'telegram'"
    float duration_seconds
    int frame_count
    jsonb events "Array of TimelineEvent objects"
    jsonb chapters "ChaptersResponse object"
    datetime created_at
    datetime processed_at
  }

  CHAT_MESSAGES {
    int id PK
    string user_id FK "ON DELETE CASCADE"
    string media_id "Nullable (NULL = free LLM chat)"
    string channel "'telegram' | 'web'"
    string role "'user' | 'assistant'"
    text content
    datetime created_at
  }

  LOGIN_CODES {
    string id PK "UUID v4"
    string user_id FK "ON DELETE CASCADE"
    string code_hash "HMAC-SHA256 digest of 6-digit OTP"
    datetime expires_at "TTL (default 5 min)"
    int attempts "Brute-force counter (max 5)"
    datetime consumed_at
  }
```

### Serverless Connection Resilience (`db/base.py`)
Neon scales idle PostgreSQL compute to zero after 5 minutes. To handle cold wakeups transparently:
- `pool_pre_ping=True` tests connections before checkout and discards closed sockets.
- `pool_recycle=300` recycles pooled connections every 5 minutes.
- `connect_timeout=10` prevents startup stalls, and `&channel_binding=require` is automatically stripped for compatibility with container `libpq` builds.

---

## 3. 🔐 Authentication & Security Flows

### Flow A: Telegram Bot Verification (`/start` or `/verify`)
1. A user opens the bot and sends `/start`.
2. **Path 1 (Mobile / Desktop App)**: The user taps the persistent `ReplyKeyboardMarkup` button **📱 Share my phone number to verify** (`request_contact=True`).
   - The bot checks `message.contact.user_id == message.from_user.id` to guarantee the contact was not forwarded from another person.
3. **Path 2 (Telegram Web Fallback)**: Because `web.telegram.org` does not render `request_contact` keyboards, the user can send `/verify +5522999185035`.
   - The bot checks that the phone is allowlisted and not already bound to a different `telegram_user_id`.
4. The phone number is normalized to **E.164** via Google's `phonenumbers` library (`normalize_phone`).
5. If found in `users` with `is_active=True`, the bot binds `user.telegram_user_id = message.from_user.id`. All subsequent Telegram messages authenticate via `from_user.id`.

### Flow B: Web Login via Phone + Telegram Bot OTP
1. The user enters their phone number in `AuthModal.tsx` → `POST /auth/otp/request`.
2. The backend normalizes the number, verifies it is on the allowlist, generates a cryptographic 6-digit code (`secrets.randbelow(1_000_000)`), stores only `HMAC-SHA256(jwt_secret, code)` in `login_codes`, and pushes the plaintext code to the user's Telegram chat via `send_telegram_text(user.telegram_user_id, ...)`.
3. The user submits the 6-digit code → `POST /auth/otp/verify`.
4. The backend verifies expiration (`300s`), attempt count (`<= 5`), and HMAC match, marks `consumed_at`, and issues a signed `HS256` **JWT** (`access_token`).

### Flow C: Web Login via Official Telegram Login Widget
1. Prerequisites: Register your web domain with `@BotFather` using `/setdomain` (e.g., `whappend.vercel.app`) and set `NEXT_PUBLIC_TELEGRAM_BOT_USERNAME` on the frontend.
2. When the user clicks the widget, Telegram returns `{ id, first_name, username, auth_date, hash }`.
3. `POST /auth/telegram-widget` computes `secret_key = SHA256(TELEGRAM_BOT_TOKEN)` and verifies `HMAC-SHA256(secret_key, data_check_string) == hash` using `hmac.compare_digest` (`verify_telegram_login_widget` in `core/security.py`).
4. If `id` matches a linked `telegram_user_id` in `users`, the backend returns a signed JWT.

### Flow D: BYOK Fernet Encryption Lifecycle
```mermaid
sequenceDiagram
  participant User as User (Web or Telegram)
  participant API as FastAPI / Bot Handler
  participant Groq as Groq API (models.list)
  participant Vault as core/security.py (Fernet)
  participant DB as Neon PostgreSQL

  User->>API: Submits gsk_xxx (PUT /me/groq-key or /setkey)
  opt Submitted via Telegram
    API->>User: Immediately deletes message with plaintext key
  end
  API->>Groq: Validate key via client.models.list()
  Groq-->>API: 200 OK (Key is active)
  API->>Vault: encrypt_api_key(gsk_xxx)
  Vault-->>API: (ciphertext, last4)
  API->>DB: Upsert into api_credentials (ciphertext, last4)
  API-->>User: Returns masked status: gsk_••••last4
```

---

## 4. 🤖 Telegram Bot Command Reference

| Command / Action | Access | Description |
|---|---|---|
| `/start` or `/help` | Everyone | Greets user, prompts for phone verification if unlinked, or shows account & key status |
| `/verify +55...` | Allowlisted | Links your allowlisted phone number on clients (like Telegram Web) that hide contact buttons |
| `/setkey [gsk_...]` | Verified | Validates your Groq API key, encrypts it in the DB, and deletes your plaintext message |
| `/key` | Verified | Displays masked key (`gsk_••••last4`), validation date, and active LLM model |
| `/removekey` | Verified | Permanently deletes your encrypted Groq key from `api_credentials` |
| `/videos` or `/media` | Verified | Shows an inline keyboard of your Web & Telegram uploads to select for Q&A |
| `/chatmode` | Verified | Detaches active media so text messages chat freely with Groq LLM |
| `/clear` | Verified | Clears conversation memory for the current chat or active media |
| `!agent <question>` | Verified | Forces the autonomous LangChain Tool-Calling Agent when querying active media |
| *(Send Video/Audio/Photo)* | Verified | Downloads media from Telegram, runs Vision/Whisper pipeline, and sets it as active media |
| `/admin_add +55... [admin]` | Admin only | Adds a phone number to the allowlist (optionally as `admin`) |
| `/admin_remove +55...` | Admin only | Removes a phone number from the allowlist |
| `/admin_list` | Admin only | Lists all allowlisted numbers, roles, Telegram link status, and key status |

---

## 5. 🌐 REST API Endpoints

### Auth & Keys
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/otp/request` | Public | Sends a 6-digit login code to an allowlisted phone via the Telegram bot |
| `POST` | `/auth/otp/verify` | Public | Verifies the 6-digit OTP and returns `{ access_token, user }` |
| `POST` | `/auth/telegram-widget` | Public | Verifies Telegram Login Widget HMAC payload and returns `{ access_token, user }` |
| `GET` | `/auth/me` | Bearer JWT | Returns current user's profile and masked BYOK key metadata |
| `GET` | `/me/groq-key` | Bearer JWT | Checks if the user has an encrypted Groq key configured |
| `PUT` | `/me/groq-key` | Bearer JWT | Validates a `gsk_...` key with Groq, encrypts it with Fernet, and saves to DB |
| `DELETE` | `/me/groq-key` | Bearer JWT | Deletes the user's stored Groq key |

### Media & RAG Q&A
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/videos` | Bearer JWT + BYOK | Uploads a video, audio, or image file and starts background AI indexing |
| `GET` | `/videos` | Bearer JWT | Lists all media owned by the authenticated user (Web + Telegram) |
| `GET` | `/videos/{id}/status` | Bearer JWT | Polls processing status (`pending`, `processing`, `completed`, `failed`) |
| `GET` | `/videos/{id}/events` | Bearer JWT | Returns extracted `TimelineEvent[]` array |
| `GET` | `/videos/{id}/media` | Bearer JWT / `?token=` | Streams the original media file with proper MIME type |
| `GET` | `/videos/{id}/chapters` | Bearer JWT + BYOK | Generates (and caches in `JSONB`) structured AI chapters via LangChain |
| `POST` | `/ask` | Bearer JWT + BYOK | Answers questions over a media timeline using Multi-Query RAG or Agent Mode |

### Admin & Webhooks
| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/admin/users` | Admin JWT | Lists all allowlisted users |
| `POST` | `/admin/users` | Admin JWT | Adds or updates an allowlisted phone number |
| `DELETE` | `/admin/users/{phone}` | Admin JWT | Removes a phone number from the allowlist |
| `POST` | `/telegram/webhook` | Header Secret | Receives Telegram `Update` payloads in production webhook mode |
| `GET` | `/health` | Public | Health check endpoint (`{"status": "ok"}`) |

---

## 6. ☁️ Production Deployment Guide (Render + Vercel + Neon)

### Step 1: Neon PostgreSQL
1. Create a free project at [neon.tech](https://neon.tech/).
2. Copy the **Postgres Connection String** (starts with `postgresql://`, **not** the HTTPS Data API URL):
   ```text
   postgresql://neondb_owner:PASSWORD@ep-xxx.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```

### Step 2: Backend on Render (Fits in Free 512 MB RAM Tier)
The backend is engineered specifically to run within Render's **512 MiB** RAM limit (`~115 MB` RSS at boot via lazy OpenCV loading and an in-memory Hybrid BM25 ranker over PostgreSQL `JSONB`, plus non-blocking lifespan startup so `$PORT` binds in `< 1s`).

- **Root Directory**: `backend`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Health Check Path**: `/health`
- **Environment Variables**:
  ```env
  PYTHON_VERSION=3.11.9
  DATABASE_URL=postgresql://neondb_owner:...@ep-...neon.tech/neondb?sslmode=require
  APP_ENCRYPTION_KEY=<from python cli.py generate-secrets>
  JWT_SECRET=<from python cli.py generate-secrets>
  ADMIN_PHONES=+5522999185035
  DEFAULT_PHONE_REGION=BR
  TELEGRAM_BOT_TOKEN=<your @BotFather token>
  TELEGRAM_WEBHOOK_URL=https://your-service.onrender.com
  TELEGRAM_WEBHOOK_SECRET=<from python cli.py generate-secrets>
  CORS_ORIGINS=https://your-app.vercel.app,http://localhost:3000
  ```
  *(Note: Never put a trailing slash `/` at the end of URLs in `CORS_ORIGINS` or `TELEGRAM_WEBHOOK_URL`.)*

### Step 3: Frontend on Vercel
1. Import the repository into Vercel and set **Root Directory** to `frontend`.
2. Add Environment Variables:
   ```env
   NEXT_PUBLIC_API_URL=https://your-service.onrender.com
   NEXT_PUBLIC_TELEGRAM_BOT_USERNAME=YourBotUsername
   ```
3. To enable the **Telegram Login Widget** on your Vercel domain, message `@BotFather` on Telegram → send `/setdomain` → select your bot → send `your-app.vercel.app`.

