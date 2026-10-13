"""Retrieve_Project_Info's answer call, pure half: render the chunks and build
the request that answers from them alone, or rejects."""

from pydantic import BaseModel, Field

from app.common.prompt_loader import load_prompt
from clients import FileSource, OpenAIParserRequest
from clients.messages import AssistantMessage

ANSWER_PROMPT_PATH = "domains/project/find_project_info/prompts/answer_from_docs.txt"

# A few sentences of answer and a few doc names, plus the reasoning tokens
# that count against this cap.
MAX_COMPLETION_TOKENS = 6_000


# Internal: the node's answer call fills this from the retrieved chunks.
# NOTE: `supported` is decided first and is the rejection — with an empty
# `answer` as the only signal, the model left real answers blank and filled in
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


def format_sources(sources: list[FileSource]) -> str:
    """The chunks in the shape the answer prompt reads: `SOURCE: <doc>
    (score: ...)` and the chunk text, `---` between."""
    return "\n\n---\n\n".join(
        f"SOURCE: {s.file_name} (score: {s.score:.3f})\n{s.content}"
        for s in sources
    )


def build_answer_request(question: str, sources: list[FileSource]) -> OpenAIParserRequest:
    """Ask the LLM to fill `ProjectDocsAnswer` from the chunks alone."""
    if not question:
        raise ValueError("No question to answer")

    return OpenAIParserRequest(
        prompt=load_prompt(prompt_path=ANSWER_PROMPT_PATH),
        prompt_path=ANSWER_PROMPT_PATH,
        # NOTE: measured on six questions x3 — gpt-5-mini was 14/18 at medium
        # and 18/18 at high but 12-25s a call; gpt-6-luna was 18/18 at 2-3s
        # and a ninth of the cost (it takes function tools only at "none").
        model="gpt-6-luna",
        reasoning_effort="none",
        # the question is the planner's (or router's) work and the chunks are
        # retrieved, so neither is something the user typed
        messages=[
            AssistantMessage(
                content=f"<question>\n{question}\n</question>\n\n"
                f"<sources>\n{format_sources(sources)}\n</sources>"
            )
        ],
        tool_models=[ProjectDocsAnswer],
        max_completion_tokens=MAX_COMPLETION_TOKENS,
    )
