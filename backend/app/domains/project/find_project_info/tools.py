from enum import Enum

from pydantic import BaseModel, Field


class ProjectInfoField(str, Enum):
    """The facts this node can look up — every member but `all` is a key of
    `PROJECT_INFO` (executor.py)."""

    NAME = "name"
    DESCRIPTION = "description"
    TECHNOLOGY_STACK = "technology_stack"
    PROJECT_URL = "project_url"
    PROJECT_GITHUB_URL = "project_github_url"
    PROJECT_GITHUB_REPO_NAME = "project_github_repo_name"
    PROJECT_GITHUB_REPO_URL = "project_github_repo_url"
    ALL = "all"


class ProjectInfoArgs(BaseModel):
    """Pick the facts about this project that the query asks for."""

    fields: list[ProjectInfoField] = Field(
        ..., json_schema_extra={"example": ["technology_stack"]}
    )
