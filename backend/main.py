import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"

# Silence ChromaDB telemetry argument mismatch bug
try:
    from chromadb.telemetry.product.posthog import Posthog
    Posthog.capture = lambda self, event: None
except Exception:
    pass

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware

from bot.app import process_webhook_update, start_bot_lifecycle, stop_bot_lifecycle
from config import settings
from core.repositories import seed_admin_phones
from db.base import init_db, session_scope
from routers import admin, ask, auth, keys, videos


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize database tables (Neon Postgres or local SQLite)
    init_db()
    # 2. Seed any ADMIN_PHONES defined in .env into the allowlist
    with session_scope() as db:
        seeded = seed_admin_phones(db)
        if seeded:
            print(f"[Startup] Seeded {seeded} admin phone number(s) from ADMIN_PHONES.")
    # 3. Start Telegram bot (webhook if TELEGRAM_WEBHOOK_URL set, otherwise long-polling)
    await start_bot_lifecycle()
    yield
    await stop_bot_lifecycle()


app = FastAPI(
    title="WhAppend API",
    description="Multimodal video/audio/image intelligence with phone-allowlist auth, encrypted BYOK Groq keys, and Telegram Bot integration",
    version="0.2.0",
    lifespan=lifespan,
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ──────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(keys.router)
app.include_router(admin.router)
app.include_router(videos.router)
app.include_router(ask.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "whappend-api"}


@app.get("/config/key-status")
async def key_status():
    """
    Returns model & BYOK policy metadata.
    `has_server_key` is always False because WhAppend runs strictly in BYOK mode.
    """
    return {
        "has_server_key": False,
        "byok_required": True,
        "provider": settings.llm_provider,
        "vision_model": settings.groq_vision_model,
        "llm_model": settings.groq_llm_model,
        "telegram_enabled": bool(settings.telegram_bot_token),
    }


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None),
):
    """Receives updates from Telegram when running in webhook mode."""
    expected = (settings.telegram_webhook_secret or "").strip()
    if expected and x_telegram_bot_api_secret_token != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook secret.")
    payload = await request.json()
    await process_webhook_update(payload)
    return {"ok": True}
