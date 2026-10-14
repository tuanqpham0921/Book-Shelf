"""`PlanJane`, the tool triage's router calls to hand the turn to the planner."""

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
