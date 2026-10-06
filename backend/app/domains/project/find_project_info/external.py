from typing import Any, Literal

from pydantic import Field

from app.domains.base_request import BaseRequest
from app.domains.base_workflow import NodeWorkflowOutput
from app.domains.node_input import NodeInput

from .labels import ProjectInfoNodeTypeEnum
from .tools import ProjectInfoArgs


class ProjectInfoRequest(BaseRequest):
    """Purpose: Retrieve information about the app, capability, tech stack, architecture, or project metadata.

    Args:
        fields: One or more ProjectInfoField values to retrieve (name,
            description, technology_stack, planjane, airglider, limitations,
            project_url,
            project_github_url,
            project_github_repo_name, project_github_repo_url, all).

    Returns: ProjectInfoOutput — the requested project facts, not a book list.

    depends_on: None — this node reads fixed project facts, not the catalog.

    Use when: the user asks about the project itself — "what tech stack does
    this use", "what is this app", "where's the GitHub repo", "tell me about
    this project".

    Do not use: when the user is commenting on or critiquing the app rather
    than asking about it.

    Constraints: fields must come from ProjectInfoField; use "all" for a
    general "tell me about this project" ask. One node covers every field
    asked for — never one node per field.

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
    """The goal text and nothing else — the facts are fixed, so nothing
    upstream could change them."""


class ProjectInfoOutput(NodeWorkflowOutput):
    """The facts asked for, keyed by `ProjectInfoField` value, in
    `PROJECT_INFO`'s order — what the reply stage answers from.

    Not book-shaped, so it subclasses `NodeWorkflowOutput` directly: no
    `num_books`, no `query`, and no book node can depend on it.

    `args` is None when the parse never happened, which is what
    `finalize_result` reads."""

    args: ProjectInfoArgs | None = None
    info: dict[str, str] = Field(default_factory=dict)

    def to_summary(self) -> dict[str, Any]:
        # the field names, not the text: the text is fixed in the code
        return {"fields": list(self.info)}
