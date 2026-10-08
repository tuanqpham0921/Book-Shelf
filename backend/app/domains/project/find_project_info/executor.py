"""The project-info node's flow — a single-call node on `find_by_title/`'s
shape: parse which facts were asked for, look them up, finalize.

The facts are fixed text rather than a table: they change when the project
does, not per request, so there is nothing to query and no store to open.
"""

from clients.messages import AssistantMessage
from app.domains.base_workflow import AppWorkflow
from clients import OpenAIParserRequest
from app.common.prompt_loader import FILL_SCHEMA_ARGS_PROMPT_PATH, load_prompt

from .tools import ProjectInfoArgs, ProjectInfoField
from .external import ProjectInfoInput, ProjectInfoOutput


# One list to fill, so the ceiling is far above anything healthy — it stops a
# runaway, it does not shape the output. Counts reasoning too.
MAX_COMPLETION_TOKENS = 1_000

# Everything the reply knows about BookShelf. Edit here when the project
# changes; every ProjectInfoField but `all` needs an entry.
PROJECT_INFO: dict[ProjectInfoField, str] = {
    ProjectInfoField.NAME: "BookShelf",
    ProjectInfoField.DESCRIPTION: (
        "BookShelf is Tuan's side project: a chat assistant for finding and "
        "recommending books from its own catalog. Before it searches, it turns "
        "each message into an explicit plan of steps, shown to the user as a "
        "diagram, then runs those steps against the catalog and writes its "
        "reply from what they found."
    ),
    ProjectInfoField.TECHNOLOGY_STACK: (
        "Python and FastAPI backend with async SQLAlchemy, streaming replies "
        "over server-sent events, deployed on Google Cloud Run. PostgreSQL with "
        "pgvector for the catalog and similarity search, hosted on Neon. OpenAI "
        "models plan each request, parse search arguments, embed descriptions "
        "and write the reply. React and Vite frontend on Firebase Hosting."
    ),
    ProjectInfoField.PLANJANE: (
        "PlanJane is BookShelf's planner. It turns each message into an "
        "explicit plan: a short list of steps, each one a capability with its "
        "own instruction and the steps it waits on, shown to the user as a "
        "diagram before anything runs. It is being built to become a service "
        "of its own."
    ),
    ProjectInfoField.AIRGLIDER: (
        "Airglider is the tracing library BookShelf runs on. Every step of a "
        "request (planning, each search, writing the reply) is recorded with "
        "its inputs, outcome, duration, tokens and cost, so a whole turn can "
        "be inspected as a tree. It lives in the BookShelf repo but depends on "
        "nothing in the app, so it can be lifted out as its own library."
    ),
    ProjectInfoField.LIMITATIONS: (
        "BookShelf is kept small on purpose, mostly to keep costs down. It "
        "does not remember earlier messages: each one is answered on its own, "
        "because sending the whole conversation with every request costs more. "
        "For the same reason it has no internet search, and knows only the "
        "books in its own catalog of about 5,000 titles. What it can do is "
        "limited too: it finds books by title, author, subject, or numbers "
        "like page count and rating, and finds books similar to ones you name. "
        "It cannot yet compare books, look up an ISBN, or pick a random book."
    ),
    ProjectInfoField.PROJECT_URL: "https://tuanqpham0921.web.app",
    ProjectInfoField.PROJECT_GITHUB_URL: "https://github.com/tuanqpham0921/Book-Shelf/",
    ProjectInfoField.PROJECT_GITHUB_REPO_NAME: "Book-Shelf",
    ProjectInfoField.PROJECT_GITHUB_REPO_URL: (
        "https://github.com/tuanqpham0921/Book-Shelf/"
    ),
}


def build_arg_parser_request(instruction: str) -> OpenAIParserRequest:
    """Ask the LLM to fill `ProjectInfoArgs` in from the planner's instruction."""
    if not instruction:
        raise ValueError("No instruction to parse arguments from")

    return OpenAIParserRequest(
        prompt=load_prompt(prompt_path=FILL_SCHEMA_ARGS_PROMPT_PATH),
        prompt_path=FILL_SCHEMA_ARGS_PROMPT_PATH,
        model="gpt-5-mini",
        reasoning_effort="minimal",
        # the instruction is the planner's own work, not something the user typed.
        messages=[AssistantMessage(content=instruction)],
        tool_models=[ProjectInfoArgs],
        max_completion_tokens=MAX_COMPLETION_TOKENS,
    )


def select_project_info(fields: list[ProjectInfoField]) -> dict[str, str]:
    """The facts asked for, in `PROJECT_INFO`'s order. `all` — or a parse that
    picked nothing — is every fact: the planner chose this node because the
    user asked about the project, so saying everything beats saying nothing."""
    if not fields or ProjectInfoField.ALL in fields:
        fields = list(PROJECT_INFO)
    return {
        field.value: text for field, text in PROJECT_INFO.items() if field in fields
    }


class ProjectInfoExecutor(AppWorkflow[ProjectInfoOutput]):
    description = "Looks up facts about BookShelf"

    ui_loading_message = "getting project info..."

    async def run(self, node_input: ProjectInfoInput) -> None:
        await self.sse_stream.send_ui_loading(self.ui_loading_message)

        # 1. parse the goal text into this node's own schema
        parsed_args: ProjectInfoArgs = await self.run_llm_args_parse(
            build_arg_parser_request(node_input.instruction)
        )
        self.result.args = parsed_args

        # 2. look the facts up — the reply stage writes them into prose
        self.result.info = select_project_info(parsed_args.fields)

        # 3. last: ok is read off the output
        self.finalize_result()

    def finalize_result(self):
        ok = self.result.args is not None and bool(self.result.info)
        return super().finalize_result(ok=ok)
