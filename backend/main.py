import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"

# Silence ChromaDB telemetry argument mismatch bug
try:
    from chromadb.telemetry.product.posthog import Posthog
    Posthog.capture = lambda self, event: None
except Exception:
    pass

from contextlib import asynccontextmanager
import asyncio
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware

from bot.app import process_webhook_update, start_bot_lifecycle, stop_bot_lifecycle
from config import settings
from core.repositories import seed_admin_phones
from db.base import init_db, session_scope
from routers import admin, ask, auth, keys, videos


async def _startup_background():
    """Runs DB table init, admin seeding, and Telegram bot startup AFTER uvicorn binds to $PORT."""
    try:
        await asyncio.to_thread(init_db)
        def _seed():
            with session_scope() as db:
                return seed_admin_phones(db)
        seeded = await asyncio.to_thread(_seed)
        if seeded:
            print(f"[Startup] Seeded {seeded} admin phone number(s) from ADMIN_PHONES.")
    except Exception as exc:
        print(f"[Startup] Database initialization error: {exc}")

    try:
        await start_bot_lifecycle()
    except Exception as exc:
        print(f"[Startup] Telegram bot startup error: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    # Fire initialization as a non-blocking task so uvicorn binds $PORT immediately for Render healthchecks
    startup_task = asyncio.create_task(_startup_background())
    yield
    if not startup_task.done():
        startup_task.cancel()
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
