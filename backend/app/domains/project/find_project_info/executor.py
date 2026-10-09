"""The project-info node's flow: search BookShelf's docs for the planner's
instruction, check the closest chunks answer it, finalize.

The chunks come from a RAG service over BookShelf's own markdown docs
(`settings.app.PROJECT_DOCS_URL`), so there is no parse and no store: the
instruction is already a self-contained question. The check is the node's one
LLM call — a question the chunks do not answer is rejected rather than
answered anyway.
"""

import httpx

from airglider import task
from app.common.prompt_loader import load_prompt
from app.domains.base_workflow import AppWorkflow
from clients import OpenAIParserRequest
from clients.messages import AssistantMessage
from config import AppConfig, settings

from .external import ProjectInfoInput, ProjectInfoOutput
from .tools import ProjectDocsAnswer

ANSWER_PROMPT_PATH = "domains/project/find_project_info/prompts/answer_from_docs.txt"

# A few sentences of answer and a few doc names, plus the reasoning tokens
# that count against this cap.
MAX_COMPLETION_TOKENS = 4_000


@task(description="Searches BookShelf's docs")
async def search_project_docs(question: str) -> str:
    """The closest chunks of the docs to `question`, as the service formats
    them: `SOURCE: <doc> (score: ...)` and the chunk text, `---` between."""
    async with httpx.AsyncClient(
        base_url=settings.app.PROJECT_DOCS_URL, timeout=AppConfig.DEFAULT_TIMEOUT
    ) as client:
        res = await client.post("/query", json={"message": question})
        res.raise_for_status()
        sources = res.json()["sources"]

    if not sources.strip():
        raise ValueError("The project docs returned no sources")
    return sources


def build_answer_request(question: str, sources: str) -> OpenAIParserRequest:
    """Ask the LLM to fill `ProjectDocsAnswer` from the chunks alone."""
    if not question:
        raise ValueError("No question to answer")

    return OpenAIParserRequest(
        prompt=load_prompt(prompt_path=ANSWER_PROMPT_PATH),
        prompt_path=ANSWER_PROMPT_PATH,
        # Measured live on six questions x3 (2026-10-08): gpt-5-mini was 14/18 at
        # medium and 18/18 at high but 12-25s a call; gpt-6-luna was 18/18 at
        # 2-3s and a ninth of the cost (it takes function tools only at "none").
        model="gpt-5-mini",
        reasoning_effort="none",
        # the question is the planner's (or router's) work and the chunks are
        # retrieved, so neither is something the user typed
        messages=[
            AssistantMessage(
                content=f"<question>\n{question}\n</question>\n\n"
                f"<sources>\n{sources}\n</sources>"
            )
        ],
        tool_models=[ProjectDocsAnswer],
        max_completion_tokens=MAX_COMPLETION_TOKENS,
    )


class ProjectInfoExecutor(AppWorkflow[ProjectInfoOutput]):
    description = "Looks up facts about BookShelf"

    ui_loading_message = "getting project info..."

    async def run(self, node_input: ProjectInfoInput) -> None:
        await self.sse_stream.send_ui_loading(self.ui_loading_message)

        # 1. the closest chunks of the docs
        question = node_input.instruction
        self.result.question = question
        sources = (await search_project_docs(question)).unwrap()

        # 2. answer from them, or reject — the reply stage writes the answer
        # into prose
        checked: ProjectDocsAnswer = await self.run_llm_args_parse(
            build_answer_request(question, sources)
        )
        if checked.supported:
            self.result.answer = checked.answer.strip()
            self.result.sources = checked.sources
        if not self.result.answer:
            self.add_details("the docs do not answer this; rejected")

        # 3. last: ok is read off the output
        self.finalize_result()

    def finalize_result(self):
        return super().finalize_result(ok=bool(self.result.answer))
