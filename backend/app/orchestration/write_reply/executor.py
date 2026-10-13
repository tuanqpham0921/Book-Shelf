"""The reply stage's flow: write the turn's reply from everything triage and
the plan produced, then send it as text and cards. `run` is the table of
contents; `render.py` is the one LLM call's pure half."""

from app.domains.base_workflow import FailedGoalOutput
from app.domains.books.base_workflow import BookReaderWorkflow
from app.domains.books.external import BookRetrievalOutput
from app.domains.books.schemas import Book
from app.domains.project.find_project_info import ProjectInfoOutput
from app.orchestration.task_runner import TaskResult
from airglider import task
from clients.messages import AssistantMessage

from .external import (
    GenerationResult,
    RecommendationsInput,
    RecommendationsOutput,
    SourceBlock,
    TextBlock,
)
from .render import books_by_handle, build_recommendations_request, render_report

# Cards land one at a time here, unlike a preview's instant dump: these are the
# recommendations, and the arrival is part of reading them.
CARD_DELAY = 0.03


# A stage, not a node: the planner cannot pick it, and the orchestrator runs it
# once per turn, after the task runner. So there is no goal — the user's own
# message is the brief — and nothing pre-selects its sources: it partitions
# every result itself. A reader workflow only for `stream_books`; it fetches
# nothing, since every node kept its preview on its output.
class GenerationExecutor(BookReaderWorkflow[RecommendationsOutput]):
    description = "Writes the reply"

    ui_loading_message = "writing a reply..."
    # the reply is the point of the turn — never folded away
    ui_section_collapsible = False

    async def run(self, node_input: RecommendationsInput) -> None:
        await self.sse_stream.send_ui_loading(self.ui_loading_message)

        # 1. split what to write from. NOTE: the orchestrator never runs this
        # over nothing, so an empty split is a caller bug, raised as one
        sources, failures = self._partition(node_input.results)
        if not sources and not failures:
            raise ValueError("Nothing to write from: the plan produced no results")
        self.add_details(
            f"writing from {len(sources)} source(s), {len(failures)} failure(s)"
        )

        # Sources first, so the report reads what was found before what could
        # not be done. One list for the report and the handles both, so a
        # handle the model copies resolves to the book it read.
        ordered = [*sources, *failures]

        # 2. the reply, as blocks — nothing reaches the browser until it is
        # whole, because each text decides which cards follow it
        reply = (await self.write_recommendations(ordered)).unwrap()
        self.result.blocks = reply.blocks

        # 3. each text, then the cards it talks about
        await self._deliver(reply.blocks, books_by_handle(ordered))

        # 4. the docs any project facts came from, for the Sources button
        docs = [
            doc
            for result in sources
            if isinstance(result.output, ProjectInfoOutput)
            for doc in result.output.sources
        ]
        if docs:
            await self.sse_stream.send_sources(list(dict.fromkeys(docs)))

        # 5. last: ok is read off the output
        self.finalize_result()

    def _partition(
        self, results: list[TaskResult]
    ) -> tuple[list[TaskResult], list[TaskResult]]:
        """The run split into what produced something to report and what did
        not.

        A source is a shape `render.py` has a rendering for: books, or the
        project facts. Anything else is dropped rather than guessed at, and
        logged as a detail.
        """
        sources: list[TaskResult] = []
        failures: list[TaskResult] = []

        for result in results:
            if isinstance(result.output, FailedGoalOutput):
                failures.append(result)
            elif isinstance(result.output, (BookRetrievalOutput, ProjectInfoOutput)):
                sources.append(result)
            else:
                self.add_details(
                    f"nothing to write from a {type(result.output).__name__}"
                )

        return sources, failures

    @task(description="Drafts the reply text")
    async def write_recommendations(
        self, results: list[TaskResult]
    ) -> GenerationResult:
        """The reply, as text blocks and the cards each one talks about.

        A `@task` so the call's spend and duration are attributed to the
        writing rather than to the sending after it.
        """
        rendered = render_report(results)
        self.result.render_evidence = rendered

        req = build_recommendations_request(rendered, self.user_message.content)
        # the report on the turn's conversation, so its trace shows what the
        # writer read
        self.messages.append(AssistantMessage(content=rendered))

        return await self.run_llm_args_parse(req)

    async def _deliver(
        self, blocks: list[TextBlock | SourceBlock], books: dict[str, Book]
    ) -> None:
        """Send the reply in the order it was written: a text as characters, a
        source as the cards it names.

        The frontend needs nothing for this — a card after text opens a card
        row, text after a card opens a paragraph. Two texts in a row land in
        one text section, so each ends on a blank line to stay a paragraph.

        `shown` spans the whole reply rather than one `stream_books` call,
        whose isbn13 dedup is per call: Dune found by title and again as its
        own neighbour is two handles and one card. A ref the report never
        printed is the model naming a book it was not given, so it is dropped.
        """
        shown: set[str | None] = set()
        for block in blocks:
            if isinstance(block, TextBlock):
                await self.sse_stream.send_chars(block.text + "\n\n")
                continue

            cards: list[Book] = []
            for ref in block.refs:
                book = books.get(ref)
                if book is None:
                    self.add_details(f"dropped ref {ref!r}: not in the report")
                elif book.isbn13 not in shown:
                    shown.add(book.isbn13)
                    cards.append(book)
            await self.stream_books(cards, delay=CARD_DELAY)

        self.result.num_books_shown = len(shown)

    def finalize_result(self) -> None:
        """ok means the turn was reported on, not that books were found.

        A reply over empty sources, or over nothing but failures, is a correct
        answer ("I don't have that, so I couldn't look for anything like it"),
        and failing it would show the generic error instead. A reply with no
        words (no blocks, or only cards) has not answered anything.
        """
        super().finalize_result(
            ok=any(
                isinstance(block, TextBlock) and block.text.strip()
                for block in self.result.blocks
            )
        )
