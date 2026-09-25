"""Triage's own tool — what the LLM fills in when it hands the turn on.

Split from `executor.py` to match the slice layout: `tools.py` is what the
LLM fills in, `executor.py` is what runs. The other two tools triage offers,
`SecurityReview` and `ClarifyingQuestion`, live in `app/common/tools.py`.
"""

from pydantic import BaseModel


class PlanJane(BaseModel):
    """Send the message to the planner, which finds the books.

    Use this whenever the message is something BookShelf supports: finding
    books by title, author, subject, pages, year or rating, books like ones
    the user loves, and questions about books or about BookShelf itself.
    """
