"""Triage's own tool — what the LLM fills in when it hands the turn on.

Split from `executor.py` to match the slice layout: `tools.py` is what the
LLM fills in, `executor.py` is what runs. Of the other three tools triage
offers, `SecurityReview` and `ClarifyingQuestion` live in `app/common/tools.py`
and `ProjectInfoArgs` is the project slice's own parse schema.
"""

from pydantic import BaseModel, Field


class PlanJane(BaseModel):
    """Send the message to the planner, which finds the books.

    Use this whenever the message is something BookShelf supports: finding
    books by title, author, subject, pages, year or rating, books like ones
    the user loves, and questions about books or about how BookShelf works.
    """

    message: str = Field(
        ...,
        description=(
            "Only when you also call ProjectInfoArgs: what is left of the "
            "user's message once the part it answers is taken out, in the "
            "user's own words. Otherwise leave it empty."
        ),
    )
