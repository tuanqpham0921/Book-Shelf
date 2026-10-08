"""The project-info node's flow: ask the project-docs service the planner's
instruction, finalize.

The answer comes from a RAG service over BookShelf's own markdown docs
(`settings.app.PROJECT_DOCS_URL`), so there is no parse and no store: the
instruction is already a self-contained question.
"""

from collections.abc import Iterable

import httpx

from airglider import task
from app.domains.base_workflow import AppWorkflow
from config import AppConfig, settings

from .external import ProjectInfoInput, ProjectInfoOutput


def join_sse_data(lines: Iterable[str]) -> str:
    """The text a server-sent-event stream of text deltas adds up to. A blank
    line ends an event, and a multi-line event's data is joined with
    newlines — that is how the service sends a newline inside a delta."""
    deltas: list[str] = []
    data: list[str] = []
    for line in [*lines, ""]:
        if line.startswith("data:"):
            data.append(line[5:].removeprefix(" "))
        elif line == "" and data:
            deltas.append("\n".join(data))
            data = []
    return "".join(deltas)


@task(description="Asks BookShelf's docs")
async def ask_project_docs(question: str) -> str:
    """One question, one answer. A new chat per question: the service keeps
    history per chat, and each BookShelf turn stands alone."""
    async with httpx.AsyncClient(
        base_url=settings.app.PROJECT_DOCS_URL, timeout=AppConfig.PROJECT_DOCS_TIMEOUT
    ) as client:
        res = await client.post("/chats")
        res.raise_for_status()
        chat_id = res.json()["id"]

        async with client.stream(
            "POST", f"/chats/{chat_id}", json={"message": question}
        ) as res:
            res.raise_for_status()
            answer = join_sse_data([line async for line in res.aiter_lines()])

    if not answer.strip():
        raise ValueError("The project docs returned an empty answer")
    return answer.strip()


class ProjectInfoExecutor(AppWorkflow[ProjectInfoOutput]):
    description = "Looks up facts about BookShelf"

    ui_loading_message = "getting project info..."

    async def run(self, node_input: ProjectInfoInput) -> None:
        await self.sse_stream.send_ui_loading(self.ui_loading_message)

        # 1. ask the docs — the reply stage writes the answer into prose
        self.result.question = node_input.instruction
        self.result.answer = (await ask_project_docs(node_input.instruction)).unwrap()

        # 2. last: ok is read off the output
        self.finalize_result()

    def finalize_result(self):
        return super().finalize_result(ok=bool(self.result.answer))
