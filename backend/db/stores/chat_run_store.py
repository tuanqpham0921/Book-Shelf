from typing import Any, Dict, List, Optional

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.schema import ChatRunModel, FeedbackModel
from .base_store import BaseStore


class ChatRunStore(BaseStore[ChatRunModel]):
    """SQLAlchemy-based chat run data access layer."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ChatRunModel)

    async def insert_run(self, row: Dict[str, Any]) -> None:
        """Insert one chat run row (keys must match ChatRunModel columns).

        Staged, not committed: the `session_factory.begin()` block this store
        was built inside flushes and commits it on exit.
        """
        self.session.add(ChatRunModel(**row))

    async def belongs_to(self, chat_id: str, session_id: str) -> bool:
        """Whether this session produced this chat run. False when there is no
        such run, including one whose turn has not been recorded yet."""
        stmt = select(
            exists().where(
                ChatRunModel.chat_id == chat_id,
                ChatRunModel.session_id == session_id,
            )
        )
        result = await self.execute_statement(stmt)
        return bool(result.scalar())

    async def get_all(
        self,
        limit: int = 200,
        offset: int = 0,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get chat runs in review-queue order: least-reviewed first (each
        run's num_reviews is derived by counting its feedback rows, never
        stored), newest first within a tie. Optionally only runs whose
        session_id contains the given search string."""
        num_reviews = func.count(FeedbackModel.id).label("num_reviews")
        stmt = (
            select(ChatRunModel, num_reviews)
            .outerjoin(FeedbackModel, FeedbackModel.chat_id == ChatRunModel.chat_id)
            .group_by(ChatRunModel.chat_id)
            .order_by(num_reviews.asc(), ChatRunModel.created_at.desc())
        )
        if session_id:
            stmt = stmt.where(ChatRunModel.session_id.ilike(f"%{session_id}%"))
        stmt = stmt.limit(limit).offset(offset)

        result = await self.execute_statement(stmt)
        return [
            {**run.to_dict(), "num_reviews": count} for run, count in result.all()
        ]
