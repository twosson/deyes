"""FastAPI application entrypoint."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    routes_agent_runs,
    routes_candidates,
    routes_content_assets,
    routes_experiments,
    routes_health,
    routes_performance,
    routes_platform_listings,
    routes_products,
    routes_recommendations,
)
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("application_starting", environment=settings.environment)
    yield
    logger.info("application_shutting_down")


app = FastAPI(
    title="Deyes Agent Layer API",
    description="Cross-border E-commerce Digital Workforce System",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(routes_health.router, prefix=settings.api_prefix, tags=["health"])
app.include_router(routes_agent_runs.router, prefix=settings.api_prefix, tags=["agent-runs"])
app.include_router(routes_candidates.router, prefix=settings.api_prefix, tags=["candidates"])

# Phase 1 中台路由
app.include_router(routes_products.router, prefix=settings.api_prefix, tags=["products"])
app.include_router(routes_content_assets.router, prefix=settings.api_prefix, tags=["content-assets"])
app.include_router(routes_platform_listings.router, prefix=settings.api_prefix, tags=["platform-listings"])

# Stage 1 Batch 3: Experiments and Performance
app.include_router(routes_experiments.router, prefix=settings.api_prefix, tags=["experiments"])
app.include_router(routes_performance.router, prefix=settings.api_prefix, tags=["performance"])

# Recommendations
app.include_router(routes_recommendations.router, prefix=settings.api_prefix, tags=["recommendations"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "deyes-agent-layer",
        "version": "0.1.0",
        "status": "running",
    }
