"""Adapter factory: creates PG or in-memory implementations based on config."""
from __future__ import annotations

import logging

from ..config import settings
from ..db.engine import is_pg_available

logger = logging.getLogger(__name__)


def create_session_repository():
    """Create session repository (PG or in-memory fallback)."""
    if is_pg_available():
        from ..session.pg_repository import PgSessionRepository

        logger.info("[Factory] Using PostgreSQL session repository")
        return PgSessionRepository()

    logger.warning(
        "[Factory] DATABASE_URL not set — using in-memory session storage. "
        "Sessions will be lost on restart. Set DATABASE_URL for persistence."
    )
    from ..session.manager import SessionManager

    return SessionManager()


def create_dlq():
    """Create DLQ (PG or in-memory fallback)."""
    if is_pg_available():
        from ..resilience.pg_dlq import PgDeadLetterQueue

        logger.info("[Factory] Using PostgreSQL dead letter queue")
        return PgDeadLetterQueue()

    logger.warning(
        "[Factory] DATABASE_URL not set — using in-memory DLQ. "
        "Dead letters will be lost on restart. Set DATABASE_URL for persistence."
    )
    from ..resilience.dead_letter import DeadLetterQueue

    return DeadLetterQueue()
