"""Preflight connectivity check for Docker, Redis, PostgreSQL/Supabase, and Gemini API."""

import asyncio
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import docker
import httpx
from docker.errors import DockerException
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from apps.api.config import get_settings, parse_arq_redis_settings
from apps.api.database import engine


def check_docker(sandbox_image: str) -> tuple[bool, str]:
    """Verify local Docker daemon is reachable and check if sandbox image exists."""
    try:
        client = docker.from_env()
        client.ping()
        images = client.images.list(name=sandbox_image)
        client.close()
        if not images:
            msg = (
                f"Docker daemon OK (warning: image '{sandbox_image}' not built yet — "
                f"run `docker build -t {sandbox_image} -f Dockerfile.sandbox .`)"
            )
            return (True, msg)
        return (True, f"Docker daemon OK, image '{sandbox_image}' ready")
    except (DockerException, OSError) as exc:
        return (False, f"Docker check failed: {exc}")


async def check_redis(redis_url: str) -> tuple[bool, str]:
    """Verify Redis Cloud / local Redis connectivity (`redis://` or `rediss://`)."""
    client: Redis | None = None
    try:
        arq_settings = parse_arq_redis_settings(redis_url)
        client = Redis.from_url(redis_url, decode_responses=True)
        pong = await client.ping()
        scheme = "TLS (rediss)" if arq_settings.ssl else "non-TLS (redis)"
        return (bool(pong), f"Redis OK ({scheme}, {arq_settings.host}:{arq_settings.port})")
    except (RedisError, OSError, ValueError) as exc:
        return (False, f"Redis check failed: {exc}")
    finally:
        if client is not None:
            await client.aclose()


async def check_postgres() -> tuple[bool, str]:
    """Verify Supabase / PostgreSQL connectivity via async SQLAlchemy engine."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return (True, "PostgreSQL / Supabase OK")
    except (SQLAlchemyError, OSError, ValueError) as exc:
        return (False, f"PostgreSQL check failed: {exc}")


async def check_gemini(api_key: str) -> tuple[bool, str]:
    """Verify Gemini API key by listing models via Google AI Studio REST endpoint."""
    if not api_key or api_key.startswith("AIzaSy..."):
        return (False, "GEMINI_API_KEY is not configured in .env")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": api_key},
            )
        if resp.status_code == 200:
            return (True, "Gemini API OK")
        return (False, f"Gemini API returned HTTP {resp.status_code}: {resp.text[:200]}")
    except (httpx.HTTPError, OSError) as exc:
        return (False, f"Gemini API check failed: {exc}")


async def run_preflight() -> int:
    settings = get_settings()
    print("=== Patchwork Preflight Check ===")

    results = [
        ("Docker Sandbox", *check_docker(settings.sandbox_image)),
        ("Redis", *(await check_redis(settings.redis_url))),
        ("Supabase/Postgres", *(await check_postgres())),
        ("Gemini API", *(await check_gemini(settings.gemini_api_key))),
    ]
    await engine.dispose()

    all_ok = True
    for name, ok, detail in results:
        badge = "PASS" if ok else "FAIL"
        print(f"[{badge}] {name}: {detail}")
        if not ok:
            all_ok = False

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_preflight()))
