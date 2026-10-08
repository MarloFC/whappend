import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"

# Silence ChromaDB telemetry argument mismatch bug
try:
    from chromadb.telemetry.product.posthog import Posthog
    Posthog.capture = lambda self, event: None
except Exception:
    pass

from typing import Optional
from pydantic import BaseModel
from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware

from routers import videos, ask


class KeyValidateRequest(BaseModel):
    api_key: Optional[str] = None

app = FastAPI(
    title="WhAppend API",
    description="Video analysis with timestamped events and LLM Q&A",
    version="0.1.0",
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
# Allow Next.js dev server (port 3000) and production domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ──────────────────────────────────────────────────────────────────
app.include_router(videos.router)
app.include_router(ask.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "whappend-api"}


@app.get("/config/key-status")
async def key_status():
    """Checks whether the backend server has a default Groq API key configured."""
    from config import settings
    has_key = bool(settings.groq_api_key and not settings.groq_api_key.startswith("gsk_your_"))
    return {
        "has_server_key": has_key,
        "provider": settings.llm_provider,
        "vision_model": settings.groq_vision_model,
        "llm_model": settings.groq_llm_model,
    }



@app.post("/auth/validate-key")
async def validate_key(
    body: Optional[KeyValidateRequest] = None,
    x_groq_api_key: Optional[str] = Header(None, alias="X-Groq-Api-Key"),
):
    """Validates if a provided Groq API key is active and authorized."""
    key = (x_groq_api_key or (body.api_key if body else "") or "").strip()
    if not key:
        return {"valid": False, "error": "No API key provided."}

    try:
        from groq import Groq
        client = Groq(api_key=key)
        # Fast query to list models to verify authentication
        client.models.list()
        return {"valid": True, "message": "Groq API key is valid and connected!"}
    except Exception as e:
        return {"valid": False, "error": str(e)}
