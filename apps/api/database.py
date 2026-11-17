"""Async SQLAlchemy engine, session factory, and database health utilities."""

import logging
from collections.abc import AsyncGenerator

from apps.api.config import get_settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)


class Base(AsyncAttrs, DeclarativeBase):
    """Base declarative class for all SQLAlchemy ORM models."""


def _build_engine() -> AsyncEngine:
    """Create the async SQLAlchemy engine configured for PostgreSQL/Supabase."""
    settings = get_settings()
    connect_args: dict[str, object] = {}
    if "asyncpg" in settings.database_url:
        # Required when connecting through Supabase Transaction Pooler (PgBouncer)
        connect_args["statement_cache_size"] = 0

    return create_async_engine(
        settings.database_url,
        echo=settings.sql_echo,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


engine: AsyncEngine = _build_engine()

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session and ensure proper cleanup."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def check_db_connection() -> bool:
    """Verify database connectivity by executing a lightweight query."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.exception("Database health check failed: %s", exc)
        return False
