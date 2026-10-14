"""Retrieve_by_Title's internal parse schema (never seen by the planner)."""

from pydantic import BaseModel, Field


class FindByTitleArgs(BaseModel):
    """Search the catalog for the book title named in the query."""

    title: str = Field(..., json_schema_extra={"example": "Dune"})
