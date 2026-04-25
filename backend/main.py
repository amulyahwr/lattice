"""Lattice — Enterprise Context Engine."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes_admin import router as admin_router
from backend.api.routes_agents import router as agents_router
from backend.api.routes_context import router as context_router
from backend.api.routes_ingest import router as ingest_router
from backend.config import settings
from backend.models.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    await init_db()
    yield


app = FastAPI(
    title="Lattice",
    description="Enterprise Context Engine — right context, right time, right agent.",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(ingest_router, prefix="/api/v1")
app.include_router(context_router, prefix="/api/v1")
app.include_router(agents_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "lattice", "version": "0.2.0"}
