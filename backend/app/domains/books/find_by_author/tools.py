from pydantic import BaseModel, Field


class FindByAuthorArgs(BaseModel):
    """Search the catalog for the author named in the query."""

    author: str = Field(..., json_schema_extra={"example": "Ursula K. Le Guin"})
