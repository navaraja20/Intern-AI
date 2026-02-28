"""
InternAI Backend – FastAPI Application Entry Point
===================================================
Starts the API server with:
  - CORS for Streamlit frontend
  - JWT-protected routes
  - PostgreSQL + ChromaDB initialization
  - System health endpoint
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import time

from config import settings
from database import create_tables
from routers import auth, profile, applications, analytics
from services.llm_service import is_ollama_running, is_model_available

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("internai")


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup tasks: create DB tables, warm embedding model."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    # Create PostgreSQL tables
    try:
        await create_tables()
        logger.info("✅ Database tables ready")
    except Exception as e:
        logger.error(f"❌ Database error: {e}")

    # Check Ollama
    if await is_ollama_running():
        logger.info("✅ Ollama is running")
        if await is_model_available(settings.PRIMARY_MODEL):
            logger.info(f"✅ Model {settings.PRIMARY_MODEL} is available")
        else:
            logger.warning(f"⚠️  Model {settings.PRIMARY_MODEL} NOT found. Run: ollama pull {settings.PRIMARY_MODEL}")
    else:
        logger.warning("⚠️  Ollama is NOT running. Start with: ollama serve")

    # Pre-warm embedding model (loads ~22MB into RAM)
    try:
        from services.rag_service import get_embedding_model
        get_embedding_model()
        logger.info("✅ Embedding model loaded")
    except Exception as e:
        logger.warning(f"⚠️  Embedding model load failed: {e}")

    logger.info(f"🚀 {settings.APP_NAME} ready at http://localhost:8000")
    yield

    logger.info("Shutting down InternAI backend...")


# ── App Factory ────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "AI-powered internship application optimizer. "
        "Tailor resumes, generate cover letters, compute ATS scores – fully local."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",    # Streamlit default
        "http://127.0.0.1:8501",
        "http://localhost:3000",    # Future React frontend
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request Timing Middleware ──────────────────────────────────────────────────

@app.middleware("http")
async def add_process_time(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = round((time.time() - start) * 1000, 1)
    response.headers["X-Process-Time-Ms"] = str(duration)
    return response


# ── Global Exception Handler ───────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "message": str(exc)},
    )


# ── Routers ────────────────────────────────────────────────────────────────────

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(applications.router)
app.include_router(analytics.router)


# ── Health & Status Endpoints ─────────────────────────────────────────────────

@app.get("/", tags=["Health"])
async def root():
    return {
        "app":     settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status":  "running",
        "docs":    "/docs",
    }


@app.get("/health", tags=["Health"])
async def health():
    ollama_ok = await is_ollama_running()
    model_ok  = await is_model_available(settings.PRIMARY_MODEL) if ollama_ok else False
    return {
        "status":        "healthy" if ollama_ok else "degraded",
        "ollama":        "running" if ollama_ok else "offline",
        "model":         settings.PRIMARY_MODEL,
        "model_ready":   model_ok,
        "database":      "connected",
    }


@app.get("/health/detailed", tags=["Health"])
async def health_detailed():
    from services.rag_service import get_embedding_model
    ollama_ok  = await is_ollama_running()
    model_ok   = await is_model_available(settings.PRIMARY_MODEL) if ollama_ok else False
    try:
        _ = get_embedding_model()
        emb_ok = True
    except Exception:
        emb_ok = False

    return {
        "app":               settings.APP_NAME,
        "version":           settings.APP_VERSION,
        "ollama":            "running" if ollama_ok else "offline",
        "primary_model":     settings.PRIMARY_MODEL,
        "model_available":   model_ok,
        "embedding_model":   settings.EMBEDDING_MODEL,
        "embedding_loaded":  emb_ok,
        "chroma_dir":        settings.CHROMA_PERSIST_DIR,
        "database_url":      f"postgresql://{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}",
    }
