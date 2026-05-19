"""PostgreSQL-backed session repository."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..db.engine import get_session
from ..db.models import MessageModel, SessionModel


class PgSessionRepository:
    """Session repository backed by PostgreSQL.

    Interface matches SessionManager for drop-in replacement.
    """

    async def get_or_create(self, session_id: str | None = None) -> dict:
        sid = session_id or f"sess_{uuid.uuid4().hex[:12]}"

        async with get_session() as db:
            result = await db.execute(
                select(SessionModel).where(SessionModel.session_id == sid)
            )
            row = result.scalar_one_or_none()

            if row is None:
                row = SessionModel(
                    session_id=sid,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(row)
                await db.commit()

            return {
                "session_id": row.session_id,
                "created_at": row.created_at.isoformat(),
                "messages": [],
            }

    async def append_message(self, session_id: str, role: str, content: str) -> None:
        async with get_session() as db:
            msg = MessageModel(
                session_id=session_id,
                role=role,
                content=content,
                created_at=datetime.now(timezone.utc),
            )
            db.add(msg)
            await db.commit()

    async def get_history(self, session_id: str) -> list[dict]:
        async with get_session() as db:
            result = await db.execute(
                select(MessageModel)
                .where(MessageModel.session_id == session_id)
                .order_by(MessageModel.id)
            )
            rows = result.scalars().all()
            return [
                {
                    "role": r.role,
                    "content": r.content,
                    "timestamp": r.created_at.isoformat(),
                }
                for r in rows
            ]

    async def set_pending_gate(self, session_id: str, gate_info: dict) -> None:
        async with get_session() as db:
            result = await db.execute(
                select(SessionModel).where(SessionModel.session_id == session_id)
            )
            row = result.scalar_one_or_none()
            if row:
                row.pending_gate_info = gate_info
                await db.commit()

    async def get_pending_gate(self, session_id: str) -> dict | None:
        async with get_session() as db:
            result = await db.execute(
                select(SessionModel.pending_gate_info).where(
                    SessionModel.session_id == session_id
                )
            )
            row = result.scalar_one_or_none()
            return row if row else None

    async def clear_pending_gate(self, session_id: str) -> None:
        async with get_session() as db:
            result = await db.execute(
                select(SessionModel).where(SessionModel.session_id == session_id)
            )
            row = result.scalar_one_or_none()
            if row:
                row.pending_gate_info = None
                await db.commit()

    async def set_execution_snapshot(self, session_id: str, snapshot: dict) -> None:
        async with get_session() as db:
            result = await db.execute(
                select(SessionModel).where(SessionModel.session_id == session_id)
            )
            row = result.scalar_one_or_none()
            if row:
                row.execution_snapshot = snapshot
                await db.commit()

    async def get_execution_snapshot(self, session_id: str) -> dict | None:
        async with get_session() as db:
            result = await db.execute(
                select(SessionModel.execution_snapshot).where(
                    SessionModel.session_id == session_id
                )
            )
            row = result.scalar_one_or_none()
            return row if row else None

    async def clear_execution_snapshot(self, session_id: str) -> None:
        async with get_session() as db:
            result = await db.execute(
                select(SessionModel).where(SessionModel.session_id == session_id)
            )
            row = result.scalar_one_or_none()
            if row:
                row.execution_snapshot = None
                await db.commit()
