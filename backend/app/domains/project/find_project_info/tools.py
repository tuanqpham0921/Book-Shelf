from enum import Enum

from pydantic import BaseModel, Field


class ProjectInfoField(str, Enum):
    """The facts this node can look up — every member but `all` is a key of
    `PROJECT_INFO` (executor.py)."""

    NAME = "name"
    DESCRIPTION = "description"
    TECHNOLOGY_STACK = "technology_stack"
    PLANJANE = "planjane"
    AIRGLIDER = "airglider"
    PROJECT_URL = "project_url"
    PROJECT_GITHUB_URL = "project_github_url"
    PROJECT_GITHUB_REPO_NAME = "project_github_repo_name"
    PROJECT_GITHUB_REPO_URL = "project_github_repo_url"
    ALL = "all"


# The docstring is the tool description two LLM calls read: the node's own
# parse, and triage's router, which offers it beside `PlanJane` so a project
# question is answered without planning. Keep it true for both.
class ProjectInfoArgs(BaseModel):
    """Pick the facts about BookShelf itself that are asked for: its name, what
    it is, its tech stack, what PlanJane (its planner) and Airglider (its
    tracing library) are, its site and its GitHub links."""

    fields: list[ProjectInfoField] = Field(
        ..., json_schema_extra={"example": ["technology_stack"]}
    )
