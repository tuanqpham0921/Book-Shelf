"""Retrieve_Project_Info's executor: search BookShelf's docs for the
instruction, answer from the closest chunks or reject, finalize.

The chunks come from an OpenAI vector store over BookShelf's own markdown docs
(`settings.openai.VECTOR_STORE_ID`), so there is no parse and no store: the
instruction is already a self-contained question.
"""

from airglider import task
from app.domains.base_workflow import AppWorkflow
from clients import FileSource

from .answer_from_docs import ProjectDocsAnswer, build_answer_request
from .external import ProjectInfoInput, ProjectInfoOutput


class ProjectInfoExecutor(AppWorkflow[ProjectInfoOutput]):
    description = "Looks up facts about BookShelf"

    ui_loading_message = "getting project info..."

    async def run(self, node_input: ProjectInfoInput) -> None:
        """Answer the instruction from the docs, or leave `answer` empty."""
        await self.sse_stream.send_ui_loading(self.ui_loading_message)

        # 1. the closest chunks of the docs
        question = node_input.instruction
        self.result.question = question
        sources = (await self.search_project_docs(question)).unwrap()

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

        # 3. finalize — ok is read off the output
        self.finalize_result()

    @task(description="Searches BookShelf's docs")
    async def search_project_docs(self, question: str) -> list[FileSource]:
        """The closest chunks of the docs to `question`, closest first."""
        sources = await self.llm_client.search_vector_store(question)
        if not sources:
            raise ValueError("The project docs returned no sources")
        return sources

    def finalize_result(self):
        # NOTE: ok means "the docs answered", unlike the book nodes — a
        # rejection fails the node so triage hands the message to the planner.
        return super().finalize_result(ok=bool(self.result.answer))
