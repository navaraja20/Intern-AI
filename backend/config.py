"""
InternAI – Central Configuration
All environment-driven settings with sane defaults.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    # ── Application ────────────────────────────────────────────────────────
    APP_NAME: str = "InternAI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ── Security ──────────────────────────────────────────────────────────
    SECRET_KEY: str = "internai-super-secret-change-in-production-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days

    # ── Database (PostgreSQL) ──────────────────────────────────────────────
    POSTGRES_USER: str = "internai"
    POSTGRES_PASSWORD: str = "internai_pass"
    POSTGRES_DB: str = "internai_db"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ── ChromaDB ──────────────────────────────────────────────────────────
    CHROMA_PERSIST_DIR: str = "./chroma_db"
    CHROMA_COLLECTION_RESUME: str = "resume_chunks"
    CHROMA_COLLECTION_EXPERIENCES: str = "experiences"
    CHROMA_COLLECTION_GITHUB: str = "github_repos"

    # ── Embeddings ────────────────────────────────────────────────────────
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"  # fastembed ONNX model, 33MB, no PyTorch
    EMBEDDING_CHUNK_SIZE: int = 400              # chars per chunk
    EMBEDDING_CHUNK_OVERLAP: int = 80

    # ── Ollama / LLM ──────────────────────────────────────────────────────
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    # Primary model – best available on user's RTX 4050 6GB
    # llama3.1:8b is already downloaded; upgrade to mixtral:8x7b-instruct-q4
    # if you have 16GB+ VRAM or run quantized offload
    PRIMARY_MODEL: str = "llama3.1:8b"
    REVIEWER_MODEL: str = "llama3.1:8b"   # same model, separate reviewer prompt
    LLM_TEMPERATURE: float = 0.25
    LLM_TOP_P: float = 0.9
    LLM_NUM_CTX: int = 8192
    LLM_TIMEOUT: int = 300               # seconds

    # ── GitHub ────────────────────────────────────────────────────────────
    GITHUB_API_BASE: str = "https://api.github.com"
    GITHUB_TOKEN: str = ""               # optional – set for higher rate limits
    GITHUB_MAX_REPOS: int = 20

    # ── ATS Scoring Weights ───────────────────────────────────────────────
    ATS_KEYWORD_WEIGHT: float = 0.40
    ATS_SEMANTIC_WEIGHT: float = 0.30
    ATS_SKILL_WEIGHT: float = 0.20
    ATS_FORMAT_WEIGHT: float = 0.10

    # ── Student Context (injected into every LLM prompt) ─────────────────
    STUDENT_CONTEXT: str = (
        "The candidate is an international master's student pursuing "
        "MSc in Data Science & Analytics at EPITA Paris. "
        "They are applying for end-of-studies internship (stage de fin d'études). "
        "All tailored outputs must reflect this academic background and internship context."
    )

    # ── RAG Settings ──────────────────────────────────────────────────────
    RAG_TOP_K: int = 5                   # chunks retrieved per query

    # ── PDF Export ────────────────────────────────────────────────────────
    PDF_FONT_SIZE: int = 10
    PDF_MARGIN_PT: int = 45

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
