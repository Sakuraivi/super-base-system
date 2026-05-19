"""Async SQLAlchemy engine and session factory."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config import settings

logger = logging.getLogger(__name__)

_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL not configured")
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_size=5,
            max_overflow=10,
        )
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def init_db():
    """Create all tables (idempotent)."""
    from .models import Base

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("[DB] Tables created/verified")


def is_pg_available() -> bool:
    """Check if DATABASE_URL is configured."""
    return bool(settings.database_url)
