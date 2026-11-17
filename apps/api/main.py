"""FastAPI application entrypoint for Patchwork."""

import asyncio

import docker
from apps.api.config import get_settings
from apps.api.database import check_db_connection
from apps.api.routers.approvals import router as approvals_router
from apps.api.routers.incidents import router as incidents_router
from apps.api.services.deduplicator import DEDUP_BLOCKED_COUNTER_KEY
from docker.errors import DockerException
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from redis.exceptions import RedisError

app = FastAPI(
    title="Patchwork API",
    version="0.1.0",
    description="Autonomous incident-response and self-healing DevOps copilot API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(incidents_router)
app.include_router(approvals_router)


def _check_docker_sync() -> bool:
    try:
        client = docker.from_env()
        client.ping()
        client.close()
        return True
    except (DockerException, OSError):
        return False


async def _check_redis_and_metrics() -> tuple[bool, int]:
    settings = get_settings()
    client: Redis | None = None
    try:
        client = Redis.from_url(settings.redis_url, decode_responses=True)
        pong = await client.ping()
        blocked_raw = await client.get(DEDUP_BLOCKED_COUNTER_KEY)
        blocked = int(blocked_raw) if blocked_raw and str(blocked_raw).isdigit() else 0
        return (bool(pong), blocked)
    except (RedisError, OSError, ValueError):
        return (False, 0)
    finally:
        if client is not None:
            await client.aclose()


@app.get("/health")
async def health_check() -> dict[str, object]:
    """Return service, database, Redis, Docker sandbox, and Gemini configuration status."""
    settings = get_settings()
    db_ok, (redis_ok, duplicates_blocked), docker_ok = await asyncio.gather(
        check_db_connection(),
        _check_redis_and_metrics(),
        asyncio.to_thread(_check_docker_sync),
    )
    gemini_ok = bool(
        settings.gemini_api_key and not settings.gemini_api_key.startswith("AIzaSy...")
    )
    all_ok = db_ok and redis_ok and docker_ok and gemini_ok
    return {
        "status": "ok" if all_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "services": {
            "fastapi": True,
            "supabase": db_ok,
            "redis": redis_ok,
            "docker_sandbox": docker_ok,
            "gemini_api": gemini_ok,
        },
        "duplicates_blocked": duplicates_blocked,
    }
