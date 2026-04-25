"""Lattice — Enterprise Contextual Layer."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes_agents import router as agents_router
from backend.api.routes_graph import router as graph_router
from backend.api.routes_search import router as search_router
from backend.api.routes_sources import router as sources_router
from backend.config import settings
from backend.models.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    await init_db()
    yield


app = FastAPI(
    title="Lattice",
    description="Enterprise contextual layer for unifying structured, unstructured, and multi-modal data sources.",
    version="0.1.0",
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
app.include_router(sources_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(agents_router, prefix="/api/v1")
app.include_router(graph_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "lattice"}
