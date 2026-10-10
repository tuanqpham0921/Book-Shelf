"""Base workflows for the books domain: count, fetch and stream books.

`BookReaderWorkflow` reads and shows books; `BookWorkflow` adds `count_books`
and is what every book-producing node subclasses.

NOTE: each call opens its own session through `ctx.store(BookStore)` and closes
it after the round trip. The turn runs after the HTTP handler returns, so a
store held for the whole request would be on a closed session.
"""

import asyncio
from abc import ABC
from typing import Any, List, Sequence, TypeVar

from airglider import task
from app.api.schemas import BookOut
from app.domains.base_workflow import AppWorkflow, NodeWorkflowOutput
from app.domains.books.external import BookRetrievalOutput
from app.domains.books.schemas import Book
from config import BookConstraints
from db.stores import DeferredBookQuery, compile_sql
from db.stores.book_store import BookStore

ReaderOutputT = TypeVar("ReaderOutputT", bound=NodeWorkflowOutput)
BookOutputT = TypeVar("BookOutputT", bound=BookRetrievalOutput)


class BookReaderWorkflow(AppWorkflow[ReaderOutputT], ABC):
    """Fetches and streams books, and writes no output field.

    Bound to `NodeWorkflowOutput` so a workflow that isn't a retrieval (the
    reply stage) can still show books.
    """

    @task(description="Fetches books to show")
    async def fetch_books(
        self, query: DeferredBookQuery, limit: int = BookConstraints.default_limit
    ) -> List[Book]:
        """Rows off a deferred query, for the caller to place.

        Ranked by the query's `score` when it has one, by rating otherwise
        (see `materialize_stmt`), so a smaller `limit` takes the best rows.
        """
        async with self.ctx.store(BookStore) as store:
            rows = await store.materialize(query, limit=limit)
        return [Book.model_validate(row) for row in rows]

    async def stream_books(
        self, books: Sequence[Book | dict[str, Any]], delay: float = 0.0
    ) -> None:
        """Stream book cards to the browser, skipping duplicate ISBNs.

        Each book is validated into `BookOut`, which keeps internal columns off
        the wire. Pass a `delay` only where the streaming is meant to be seen.
        """
        # NOTE: a row with no `isbn13` raises — it is the card list's React key
        sent_isbn = set()
        for i, book in enumerate(books):
            card = BookOut.model_validate(book, from_attributes=True)
            if card.isbn13 in sent_isbn:
                continue

            await self.sse_stream.send_book_card(position=i, data=card.model_dump())
            if delay:
                await asyncio.sleep(delay)
            sent_isbn.add(card.isbn13)


class BookWorkflow(BookReaderWorkflow[BookOutputT], ABC):
    """Base for every book-producing node: the reader plus `count_books`."""

    @task(description="Counts matching books")
    async def count_books(self, query: DeferredBookQuery) -> int:
        """Stamp the query on the output and count it — no rows fetched.

        Writes `query` (what downstream nodes compose against), `query_sql`
        (the readable copy that reaches `chat_runs`) and `num_books`.
        """
        # stamped before the session opens, so a failed count still records SQL
        self.result.query = query
        self.result.query_sql = compile_sql(query.stmt)

        async with self.ctx.store(BookStore) as store:
            total = await store.count(query)
        self.result.num_books = total
        return total
