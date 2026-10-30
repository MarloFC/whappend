from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    # ── LLM Provider ──────────────────────────────────────────────────────────
    # Options: "openai" | "groq"
    llm_provider: str = Field("groq", env="LLM_PROVIDER")

    # OpenAI (optional)
    openai_api_key: str = Field("", env="OPENAI_API_KEY")
    openai_vision_model: str = Field("gpt-4o", env="OPENAI_VISION_MODEL")
    openai_llm_model: str = Field("gpt-4o-mini", env="OPENAI_LLM_MODEL")
    openai_embedding_model: str = Field("text-embedding-3-small", env="OPENAI_EMBEDDING_MODEL")

    # Groq — BYOK only. There is intentionally NO server-side GROQ_API_KEY:
    # every request uses the key the authenticated user stored (encrypted) in the DB.
    groq_vision_model: str = Field("qwen/qwen3.8-27b", env="GROQ_VISION_MODEL")
    groq_llm_model: str = Field("qwen/qwen3.8-27b", env="GROQ_LLM_MODEL")

    # ── Embeddings ────────────────────────────────────────────────────────────
    # Options: "local" (sentence-transformers) | "openai"
    embedding_provider: str = Field("local", env="EMBEDDING_PROVIDER")
    local_embedding_model: str = Field("all-MiniLM-L6-v2", env="LOCAL_EMBEDDING_MODEL")

    # ── Mock mode (no API calls at all) ──────────────────────────────────────
    mock_mode: bool = Field(False, env="MOCK_MODE")

    # ── Storage ───────────────────────────────────────────────────────────────
    storage_dir: Path = Field(Path("./storage"), env="STORAGE_DIR")
    chroma_dir: Path = Field(Path("./storage/chroma"), env="CHROMA_DIR")

    # ── Processing config ─────────────────────────────────────────────────────
    frame_interval_seconds: int = Field(2, env="FRAME_INTERVAL_SECONDS")
    frame_batch_size: int = Field(4, env="FRAME_BATCH_SIZE")
    max_video_size_mb: int = Field(500, env="MAX_VIDEO_SIZE_MB")

    # ── Database ──────────────────────────────────────────────────────────────
    # Neon: postgresql://user:pass@ep-xxx.region.aws.neon.tech/neondb?sslmode=require
    # Empty → local SQLite file (dev only).
    database_url: str = Field("", env="DATABASE_URL")

    # ── Security ──────────────────────────────────────────────────────────────
    # Fernet key used to encrypt users' Groq keys at rest. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    app_encryption_key: str = Field("", env="APP_ENCRYPTION_KEY")
    # Secret used to sign JWT session tokens. Generate with:
    #   python -c "import secrets; print(secrets.token_urlsafe(48))"
    jwt_secret: str = Field("", env="JWT_SECRET")
    jwt_expire_minutes: int = Field(60 * 24 * 7, env="JWT_EXPIRE_MINUTES")

    # Comma-separated phone numbers that are auto-created as admins on startup.
    admin_phones: str = Field("", env="ADMIN_PHONES")
    # Region used to parse phone numbers typed without a country code (+55 → "BR").
    default_phone_region: str = Field("BR", env="DEFAULT_PHONE_REGION")

    # OTP login (code delivered through the Telegram bot)
    otp_ttl_seconds: int = Field(300, env="OTP_TTL_SECONDS")
    otp_max_attempts: int = Field(5, env="OTP_MAX_ATTEMPTS")

    # ── Telegram ──────────────────────────────────────────────────────────────
    telegram_bot_token: str = Field("", env="TELEGRAM_BOT_TOKEN")
    # Public HTTPS base URL (e.g. https://api.example.com). Empty → long polling (dev).
    telegram_webhook_url: str = Field("", env="TELEGRAM_WEBHOOK_URL")
    telegram_webhook_secret: str = Field("", env="TELEGRAM_WEBHOOK_SECRET")
    # Optional Redis (e.g. Upstash free tier) for bot conversation state.
    redis_url: str = Field("", env="REDIS_URL")

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: str = Field("http://localhost:3000,http://localhost:3001", env="CORS_ORIGINS")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def admin_phone_list(self) -> list[str]:
        return [p.strip() for p in self.admin_phones.split(",") if p.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

# Ensure storage dirs exist
(settings.storage_dir / "videos").mkdir(parents=True, exist_ok=True)
(settings.storage_dir / "frames").mkdir(parents=True, exist_ok=True)
settings.chroma_dir.mkdir(parents=True, exist_ok=True)
