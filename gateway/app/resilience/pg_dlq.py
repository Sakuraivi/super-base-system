"""PostgreSQL-backed Dead Letter Queue."""
from __future__ import annotations

from sqlalchemy import delete, func, select, update

from ..db.engine import get_session
from ..db.models import DeadLetterModel
from .dead_letter import DeadLetter


class PgDeadLetterQueue:
    """DLQ backed by PostgreSQL.

    Interface matches DeadLetterQueue for drop-in replacement.
    """

    async def push(self, letter: DeadLetter) -> None:
        async with get_session() as db:
            row = DeadLetterModel(
                dlq_id=letter.dlq_id,
                task_id=letter.task_id,
                module_id=letter.module_id,
                error=letter.error,
                retry_count=letter.retry_count,
                payload=letter.payload,
                created_at=letter.created_at,
                replayed=letter.replayed,
            )
            db.add(row)
            await db.commit()

    async def list(
        self, limit: int = 50, module_id: str | None = None
    ) -> list[DeadLetter]:
        async with get_session() as db:
            stmt = select(DeadLetterModel).order_by(DeadLetterModel.created_at.desc())
            if module_id:
                stmt = stmt.where(DeadLetterModel.module_id == module_id)
            stmt = stmt.limit(limit)

            result = await db.execute(stmt)
            rows = result.scalars().all()
            return [self._to_pydantic(r) for r in rows]

    async def get(self, dlq_id: str) -> DeadLetter | None:
        async with get_session() as db:
            result = await db.execute(
                select(DeadLetterModel).where(DeadLetterModel.dlq_id == dlq_id)
            )
            row = result.scalar_one_or_none()
            return self._to_pydantic(row) if row else None

    async def count(self, module_id: str | None = None) -> int:
        async with get_session() as db:
            stmt = select(func.count(DeadLetterModel.dlq_id))
            if module_id:
                stmt = stmt.where(DeadLetterModel.module_id == module_id)
            result = await db.execute(stmt)
            return result.scalar_one()

    async def mark_replayed(self, dlq_id: str) -> bool:
        async with get_session() as db:
            result = await db.execute(
                update(DeadLetterModel)
                .where(DeadLetterModel.dlq_id == dlq_id)
                .values(replayed=True)
            )
            await db.commit()
            return result.rowcount > 0

    async def clear(self) -> int:
        async with get_session() as db:
            result = await db.execute(delete(DeadLetterModel))
            await db.commit()
            return result.rowcount

    @staticmethod
    def _to_pydantic(row: DeadLetterModel) -> DeadLetter:
        return DeadLetter(
            dlq_id=row.dlq_id,
            task_id=row.task_id,
            module_id=row.module_id,
            error=row.error,
            retry_count=row.retry_count,
            payload=row.payload or {},
            created_at=row.created_at.isoformat() if row.created_at else "",
            replayed=row.replayed,
        )
