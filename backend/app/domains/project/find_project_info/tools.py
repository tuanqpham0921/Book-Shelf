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


# Internal: the node's check call fills this from the retrieved chunks.
# `supported` is decided first and is the rejection: with an empty `answer` as
# the only signal, the model left real answers blank and filled in
# non-answers ("the docs do not say...") about as often as not.
class ProjectDocsAnswer(BaseModel):
    """Decide whether the documentation chunks answer the question about
    BookShelf, then answer it from those chunks alone."""

    supported: bool = Field(
        ...,
        description=(
            "True when the chunks state the answer to the question. False "
            "when they are only on a nearby topic."
        ),
    )
    sources: list[str] = Field(
        ...,
        description=(
            "The doc names (from the SOURCE lines) of the chunks the answer "
            "rests on, each once. Empty when not supported."
        ),
        json_schema_extra={"example": ["bookshelf/docs/deployment.md"]},
    )
    answer: str = Field(
        ...,
        description=(
            "The answer, using only what those chunks state. Empty when not "
            "supported."
        ),
    )
