"""The query decomposition's tool-call schema — what the LLM fills in.

Split from `executor.py` to match the slice layout: `schemas.py` is what the
LLM fills in, `executor.py` is what runs. The portions it carries are in
`external.py`, because they outlive the tool call.
"""

from pydantic import BaseModel, Field

from app.common.field_types import MAX_STRING_LENGTH, ReasoningStr

from .external import QueryPortion


class QueryDecomposition(BaseModel):
    """Split the user's message into portions and label each one.

    An internal tool like a slice's `*Args` — never seen by the planner, so no
    `node_type`. `reasoning` comes first so the model justifies before it
    labels; it is kept for the trace and never shown to the user.
    """

    reasoning: ReasoningStr = Field(
        ...,
        max_length=MAX_STRING_LENGTH,
        json_schema_extra={"example": "A greeting, then a request for similar books"},
    )
    portions: list[QueryPortion] = Field(..., min_length=1)
