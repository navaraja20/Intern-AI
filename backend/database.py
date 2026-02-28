"""
SQLAlchemy async engine + ChromaDB client setup.
Single source of truth for all database sessions.
"""

from __future__ import annotations
from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.api import ClientAPI as ChromaClient

from config import settings


# ── SQLAlchemy Async Engine ───────────────────────────────────────────────────

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency – yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_tables() -> None:
    """Create all tables (called at startup)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ── ChromaDB Client ───────────────────────────────────────────────────────────

def get_chroma_client() -> ChromaClient:
    """Return a persistent ChromaDB client (singleton-safe)."""
    return chromadb.PersistentClient(
        path=settings.CHROMA_PERSIST_DIR,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


_chroma_client: Optional[ChromaClient] = None


def chroma_client() -> ChromaClient:
    """Lazy singleton ChromaDB client."""
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = get_chroma_client()
    return _chroma_client


def get_chroma_collection(name: str) -> chromadb.Collection:
    """Get or create a ChromaDB collection by name."""
    return chroma_client().get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )
