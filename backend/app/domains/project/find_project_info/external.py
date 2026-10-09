from typing import Any, Literal

from app.domains.base_request import BaseRequest
from app.domains.base_workflow import NodeWorkflowOutput
from app.domains.node_input import NodeInput

from .labels import ProjectInfoNodeTypeEnum


class ProjectInfoRequest(BaseRequest):
    """Purpose: Answer a question about the app, capability, tech stack, architecture, or project metadata, from BookShelf's own documentation.

    Args: None — the instruction is the question, sent as written, so it must
        stand alone: name what is asked about rather than "it" or "this".

    Returns: ProjectInfoOutput — an answer about the project, not a book list.

    depends_on: None — this node reads the project's docs, not the catalog.

    Use when: the user asks about the project itself — "what tech stack does
    this use", "what is this app", "where's the GitHub repo", "tell me about
    this project".

    Do not use: when the user is commenting on or critiquing the app rather
    than asking about it.

    Constraints: One node covers every project question in the message —
    never one node per question. Keep the query concise and only one sentence.

    Example queries:
        - "what tech stack does this use"
        - "what is this app"
        - "where's the GitHub repo"
        - "tell me about this project"
        - "what can you do?"
        - "why is coversation only single turn? what was the rationale?"
        - "how long did this project take or cost to run?"
    """

    node_type: Literal[ProjectInfoNodeTypeEnum.REQUEST] = ProjectInfoNodeTypeEnum.REQUEST


class ProjectInfoInput(NodeInput):
    """The goal text and nothing else — the docs are fixed, so nothing
    upstream could change them."""


class ProjectInfoOutput(NodeWorkflowOutput):
    """The question sent to the project docs, the answer checked against the
    closest chunks, and the docs it rests on — what the reply stage answers
    from.

    Not book-shaped, so it subclasses `NodeWorkflowOutput` directly: no
    `num_books`, no `query`, and no book node can depend on it.

    `answer` is empty when the docs were never asked or do not answer the
    question, which is what `finalize_result` reads."""

    question: str = ""
    answer: str = ""
    sources: list[str] = []

    def to_summary(self) -> dict[str, Any]:
        return {"question": self.question, "answer": self.answer, "sources": self.sources}
