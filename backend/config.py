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

    # Groq (free tier — get key at console.groq.com)
    groq_api_key: str = Field("", env="GROQ_API_KEY")
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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# Ensure storage dirs exist
(settings.storage_dir / "videos").mkdir(parents=True, exist_ok=True)
(settings.storage_dir / "frames").mkdir(parents=True, exist_ok=True)
settings.chroma_dir.mkdir(parents=True, exist_ok=True)
