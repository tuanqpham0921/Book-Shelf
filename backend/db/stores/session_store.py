from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from config import AppConfig
from db.schema import SessionModel
from .base_store import BaseStore


class SessionStore(BaseStore[SessionModel]):
    """SQLAlchemy-based session token-budget data access layer.

    "Session" here is the chat session, not the SQLAlchemy one — `self.session`
    is the latter, which is the split `get_sqlalchemy_session` already names on
    the dependency side.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(session, SessionModel)

    async def start_turn(self, session_id: str) -> int:
        """Mark a session as starting a turn and return the tokens it has left,
        creating it with a full budget if this is its first.

        One round trip, which is why the conflict branch is DO UPDATE rather
        than DO NOTHING: DO NOTHING returns no row when the row already exists —
        the common case, every message after the first — so the caller would
        need a second SELECT to read the balance. Touching `last_updated` is
        both what makes RETURNING give a row and exactly what the conflict
        means, since a session's first message and its tenth are the same event.
        A turn that is then refused still counts as activity.

        The balance comes back as a plain int rather than the model, and that is
        load-bearing: `returning(SessionModel)` hands back an *ORM entity*, so a
        session whose identity map already holds this row returns the copy it
        remembers — which `debit` deliberately does not update
        (`synchronize_session=False`), and which `expire_on_commit=False` never
        refreshes. Measured returning a stale full budget for an overdrawn
        session. A scalar cannot go stale.
        """
        stmt = (
            insert(SessionModel)
            .values(
                session_id=session_id,
                remaining_tokens=AppConfig.SESSION_TOKEN_BUDGET,
            )
            .on_conflict_do_update(
                index_elements=[SessionModel.session_id],
                set_={"last_updated": func.now()},
            )
            .returning(SessionModel.remaining_tokens)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.scalar_one()

    async def debit(self, session_id: str, spent: int) -> int | None:
        """Charge `spent` tokens to a session, returning the new balance — or
        None when there is no such row.

        The subtraction happens in SQL, not in Python: two turns overlapping in
        one session (two browser tabs) each hold their own database session, so
        a read-modify-write would lose one of the debits. That also means the
        balance can end up negative, which is allowed — see SessionModel.

        `synchronize_session=False` because this runs on a session opened for
        this one statement, with nothing in its identity map to synchronize;
        the default "auto" strategy would try to evaluate the arithmetic in
        Python first.
        """
        stmt = (
            update(SessionModel)
            .where(SessionModel.session_id == session_id)
            .values(
                remaining_tokens=SessionModel.remaining_tokens - spent,
                last_updated=func.now(),
            )
            .returning(SessionModel.remaining_tokens)
            .execution_options(synchronize_session=False)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        # None rather than a raise: the caller is the orchestrator's cleanup,
        # where a missing row is worth a warning and nothing more.
        return result.scalar_one_or_none()
