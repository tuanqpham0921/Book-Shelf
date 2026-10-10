"""Retrieve_by_Title's executor: parse a title, count the matches, preview a few."""

from app.common.prompt_loader import FILL_SCHEMA_ARGS_PROMPT_PATH, load_prompt
from app.domains.books.base_workflow import BookWorkflow
from clients import OpenAIParserRequest
from clients.messages import AssistantMessage
from db.stores import title_query

from .external import FindByTitleInput, FindByTitleOutput
from .tools import FindByTitleArgs

# one field to fill, so this sits far above a healthy reply — it stops a
# runaway, it doesn't shape the output (reasoning counts against it)
MAX_COMPLETION_TOKENS = 1_000


class FindByTitleExecutor(BookWorkflow[FindByTitleOutput]):
    description = "Finds books by title"

    ui_loading_message = "getting books by title..."

    async def run(self, node_input: FindByTitleInput) -> None:
        """Count the matching titles and hand the query downstream, not the rows."""
        await self.sse_stream.send_ui_loading(self.ui_loading_message)

        # 1. parse the planner's instruction into FindByTitleArgs
        parsed_args: FindByTitleArgs = await self.run_llm_args_parse(
            build_arg_parser_request(node_input.instruction)
        )
        self.result.args = parsed_args

        if not parsed_args.title:
            raise ValueError("No title was parsed")

        # 2. build the query and count — no rows fetched
        deferred = title_query(title=parsed_args.title)
        total = (await self.count_books(deferred)).unwrap()

        # 3. preview cards, only when something matched
        # NOTE: downstream nodes read `self.result.query` (every match), never
        # `preview` — it is only for the cards, the record and the reply.
        if total:
            self.result.preview = (await self.fetch_books(deferred)).unwrap()
            await self.stream_books(self.result.preview)

        # 4. finalize — ok is read off the output
        self.finalize_result()

    def finalize_result(self):
        # NOTE: ok means "the query got built", not "something matched" —
        # zero matches is an answer, not a failure.
        ok = self.result.args is not None and self.result.query is not None
        return super().finalize_result(ok=ok)


def build_arg_parser_request(instruction: str) -> OpenAIParserRequest:
    """Ask the LLM to fill `FindByTitleArgs` in from the planner's instruction."""
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
        tool_models=[FindByTitleArgs],
        max_completion_tokens=MAX_COMPLETION_TOKENS,
    )
