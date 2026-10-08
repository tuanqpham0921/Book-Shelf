from pydantic import BaseModel, Field


# The docstring is the tool description triage's router reads: it offers this
# beside `PlanJane` so a project question is answered without planning.
class ProjectInfoArgs(BaseModel):
    """Ask BookShelf's own documentation a question about BookShelf itself: its
    name, what it is, its tech stack, what PlanJane (its planner) and Airglider
    (its tracing library) are, what it cannot do, its site and its GitHub
    links."""

    question: str = Field(
        ...,
        description=(
            "The question about BookShelf, in the user's words, standing alone "
            "without the rest of the message."
        ),
        json_schema_extra={"example": "What tech stack does BookShelf use?"},
    )
