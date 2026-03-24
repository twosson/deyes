"""Health check endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.redis import RedisClient
from app.clients.sglang import SGLangClient
from app.core.logging import get_logger
from app.db.session import get_db

logger = get_logger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check():
    """Basic health check."""
    return {"status": "healthy"}


@router.get("/health/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """Readiness check with dependency validation."""
    checks = {
        "database": "unknown",
        "redis": "unknown",
        "sglang": "unknown",
    }

    # Check database
    try:
        result = await db.execute(text("SELECT 1"))
        if result.scalar() == 1:
            checks["database"] = "healthy"
    except Exception as e:
        logger.error("database_health_check_failed", error=str(e))
        checks["database"] = "unhealthy"

    # Check Redis
    try:
        redis_client = RedisClient()
        await redis_client.set("health_check", "ok", ex=10)
        value = await redis_client.get("health_check")
        if value == "ok":
            checks["redis"] = "healthy"
        await redis_client.close()
    except Exception as e:
        logger.error("redis_health_check_failed", error=str(e))
        checks["redis"] = "unhealthy"

    # Check SGLang
    try:
        sglang_client = SGLangClient()
        response = await sglang_client.chat_completion(
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=10,
        )
        if response.get("choices"):
            checks["sglang"] = "healthy"
        await sglang_client.close()
    except Exception as e:
        logger.error("sglang_health_check_failed", error=str(e))
        checks["sglang"] = "unhealthy"

    overall_healthy = all(status == "healthy" for status in checks.values())

    return {
        "status": "healthy" if overall_healthy else "degraded",
        "checks": checks,
    }
