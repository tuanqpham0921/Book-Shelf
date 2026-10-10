"""Retrieve_by_Author's executor: parse an author, count their books, preview a few."""

from app.common.prompt_loader import FILL_SCHEMA_ARGS_PROMPT_PATH, load_prompt
from app.domains.books.base_workflow import BookWorkflow
from clients import OpenAIParserRequest
from clients.messages import AssistantMessage
from db.stores import author_query

from .external import FindByAuthorInput, FindByAuthorOutput
from .tools import FindByAuthorArgs

# one field to fill; see find_by_title/executor.py for the sizing rule
MAX_COMPLETION_TOKENS = 1_000


class FindByAuthorExecutor(BookWorkflow[FindByAuthorOutput]):
    description = "Finds books by author"

    ui_loading_message = "getting books by author..."

    async def run(self, node_input: FindByAuthorInput) -> None:
        """Count the author's books and hand the query downstream, not the rows."""
        await self.sse_stream.send_ui_loading(self.ui_loading_message)

        # 1. parse the planner's instruction into FindByAuthorArgs
        parsed_args: FindByAuthorArgs = await self.run_llm_args_parse(
            build_arg_parser_request(node_input.instruction)
        )
        self.result.args = parsed_args

        if not parsed_args.author:
            raise ValueError("No author was parsed")

        # 2. build the query and count — no rows fetched
        deferred = author_query(author=parsed_args.author)
        total = (await self.count_books(deferred)).unwrap()

        # 3. preview cards, only when something matched
        # NOTE: downstream nodes read `self.result.query` (the whole
        # bibliography), never `preview`.
        if total:
            self.result.preview = (await self.fetch_books(deferred)).unwrap()
            await self.stream_books(self.result.preview)

        # 4. finalize — ok is read off the output
        self.finalize_result()

    def finalize_result(self):
        # NOTE: ok means "the query got built", not "something matched" — an
        # unknown author is an answer, and the empty half of a "did X write Y?"
        # intersect.
        ok = self.result.args is not None and self.result.query is not None
        return super().finalize_result(ok=ok)


def build_arg_parser_request(instruction: str) -> OpenAIParserRequest:
    """Ask the LLM to fill `FindByAuthorArgs` in from the planner's instruction."""
    if not instruction:
        raise ValueError("No instruction to parse arguments from")

    return OpenAIParserRequest(
        prompt=load_prompt(prompt_path=FILL_SCHEMA_ARGS_PROMPT_PATH),
        prompt_path=FILL_SCHEMA_ARGS_PROMPT_PATH,
        model="gpt-5-nano",
        reasoning_effort="minimal",
        # the planner wrote the instruction, so it goes in as an assistant turn
        # NOTE: single-turn only — earlier messages belong here once
        # conversations carry them.
        messages=[AssistantMessage(content=instruction)],
        tool_models=[FindByAuthorArgs],
        max_completion_tokens=MAX_COMPLETION_TOKENS,
    )
