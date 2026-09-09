"""The title node answering in words — the second brief, end to end.

`Retrieve_by_Title` is normally working material for the goal after it: it
counts, streams a few cards and says nothing. When the plan carries a
`generation_instruction` for it ("do you have Dune?") it also writes a sentence,
and that switch is what this file pins.

Faked at the boundary and nowhere inside it: `store.count` and
`store.materialize` for the round trips, `run_llm_args_parse` for the argument
parse and `run_llm_call` for the reply. The real `title_query`, the real
`@task` envelopes, the real facts renderer and the real `finalize_result` all
run.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domains.books.external import BookRequestContext
from app.domains.books.find_by_title.executor import (
    FindByTitleExecutor,
    render_title_facts,
)
from app.domains.books.find_by_title.external import FindByTitleInput
from app.domains.books.find_by_title.schemas import FindByTitleArgs
from app.domains.books.schemas import Book
from clients.messages import AssistantMessage
from db.stores import BookStore

ROW = {
    "isbn13": "9780441013593",
    "title": "Dune",
    "authors": "Frank Herbert",
    "genre": "Fiction",
    "num_pages": 604,
}

ASKED_TO_SAY = "Confirm whether Dune is in the catalogue"


@pytest.fixture
def node(request_context):
    """The executor with both boundaries stubbed, ready to run."""
    store = request_context.stores[BookStore]
    # a real query object: `count_books` compiles it to SQL, which a MagicMock
    # cannot stand in for
    real = BookStore(MagicMock())
    store.title_query = real.title_query
    store.count = AsyncMock(return_value=3)
    store.materialize = AsyncMock(return_value=[ROW])

    wf = FindByTitleExecutor(BookRequestContext.narrow(request_context))
    wf.run_llm_args_parse = AsyncMock(return_value=FindByTitleArgs(title="Dune"))
    # a real `AssistantMessage` so `reply_to_user` can count its words, and so
    # what the writer was *sent* stays inspectable
    wf.run_llm_call = AsyncMock(
        return_value=AssistantMessage(content="Yes, Dune is here.")
    )
    return wf


def _facts_sent_to_the_writer(node) -> str:
    """The block the reply request carried — all the writer was told."""
    node.run_llm_call.assert_awaited_once()
    return node.run_llm_call.await_args.args[0].messages[0].content


class TestSilentByDefault:
    @pytest.mark.asyncio
    async def test_a_plain_lookup_writes_no_reply(self, node):
        """Most title lookups are a step in someone else's chain. Speaking on
        every one of them would narrate the machinery."""
        result = await node(FindByTitleInput(instruction="Find the book Dune"))

        assert result.ok, result.runtime_error
        node.run_llm_call.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_it_still_streams_the_count_line(self, node, monkeypatch):
        sent: list[str] = []
        monkeypatch.setattr(
            node.sse_stream, "send_chars", AsyncMock(side_effect=lambda d: sent.append(d))
        )

        await node(FindByTitleInput(instruction="Find the book Dune"))

        assert any("Found 3 books titled: Dune" in line for line in sent)


class TestAskedToSpeak:
    @pytest.mark.asyncio
    async def test_a_goal_with_a_second_brief_gets_a_reply(self, node):
        result = await node(
            FindByTitleInput(
                instruction="Find the book Dune",
                generation_instruction=ASKED_TO_SAY,
            )
        )

        assert result.ok, result.runtime_error
        node.run_llm_call.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_the_brief_reaches_the_writer_as_a_fact(self, node):
        """Appended by `run_llm_reply` to the facts block, never to the prompt:
        it is planner prose paraphrasing an untrusted message."""
        await node(
            FindByTitleInput(
                instruction="Find the book Dune",
                generation_instruction=ASKED_TO_SAY,
            )
        )

        assert f"- asked to say: {ASKED_TO_SAY}" in _facts_sent_to_the_writer(node)

    @pytest.mark.asyncio
    async def test_the_count_line_is_dropped_when_it_speaks(self, node, monkeypatch):
        """The section is expanded when a goal replies, so a machine bullet
        would sit directly above prose forbidden from sounding technical."""
        sent: list[str] = []
        monkeypatch.setattr(
            node.sse_stream, "send_chars", AsyncMock(side_effect=lambda d: sent.append(d))
        )

        await node(
            FindByTitleInput(
                instruction="Find the book Dune",
                generation_instruction=ASKED_TO_SAY,
            )
        )

        assert not any("Found 3 books titled" in line for line in sent)

    @pytest.mark.asyncio
    async def test_a_failed_writer_does_not_fail_the_lookup(self, node):
        """The query is a real artifact the next goal composes against, so a
        writer that raises costs the turn its sentence, not its search."""
        node.run_llm_call = AsyncMock(side_effect=RuntimeError("writer is down"))

        result = await node(
            FindByTitleInput(
                instruction="Find the book Dune",
                generation_instruction=ASKED_TO_SAY,
            )
        )

        assert result.ok, result.runtime_error
        assert result.unwrap().query is not None


class TestNothingFound:
    @pytest.mark.asyncio
    async def test_it_speaks_when_the_catalogue_has_nothing(self, node):
        """"I don't have Dune" is the reply this exists to write, and it is
        written from an empty set — so the call sits outside the `if total`."""
        node.ctx.store.count = AsyncMock(return_value=0)

        result = await node(
            FindByTitleInput(
                instruction="Find the book Dune",
                generation_instruction=ASKED_TO_SAY,
            )
        )

        assert result.ok, result.runtime_error
        assert "0 in the catalogue" in _facts_sent_to_the_writer(node)

    @pytest.mark.asyncio
    async def test_it_fetches_no_rows(self, node):
        node.ctx.store.count = AsyncMock(return_value=0)

        await node(
            FindByTitleInput(
                instruction="Find the book Dune",
                generation_instruction=ASKED_TO_SAY,
            )
        )

        node.ctx.store.materialize.assert_not_awaited()


class TestTheFactsBlock:
    """`render_title_facts` on its own — what the writer is allowed to know."""

    def test_both_counts_are_stated(self):
        """The honesty guard: a preview is capped, so forty editions put three
        on screen. Without both numbers the writer describes three as all."""
        facts = render_title_facts("Dune", "Find Dune", 40, [Book(**ROW)])

        assert "- 40 in the catalogue under that title" in facts
        assert "- 1 of them on screen" in facts

    def test_an_empty_catalogue_states_no_screen_count(self):
        facts = render_title_facts("Dune", "Find Dune", 0, [])

        assert "- 0 in the catalogue under that title" in facts
        assert "on screen" not in facts

    def test_authors_are_counted_not_listed_per_book(self):
        facts = render_title_facts("Dune", "Find Dune", 2, [Book(**ROW), Book(**ROW)])

        assert "- by: Frank Herbert (2)" in facts

    def test_descriptions_never_reach_the_writer(self):
        """Nothing in the facts describes the book — this reply confirms a
        title, and a writer handed a blurb reviews it."""
        book = Book(**ROW, description="A desert planet and its spice.")
        facts = render_title_facts("Dune", "Find Dune", 1, [book])

        assert "desert" not in facts
