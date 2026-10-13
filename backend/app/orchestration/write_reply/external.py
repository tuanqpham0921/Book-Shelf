"""The reply stage's shapes: `RecommendationsInput` from the orchestrator,
`GenerationResult` the writer fills in, `RecommendationsOutput` for `chat_runs`."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domains.base_workflow import NodeWorkflowOutput
from app.domains.node_input import WorkflowInput
from app.orchestration.task_runner import TaskResult


class RecommendationsInput(WorkflowInput):
    """Everything triage and the plan produced, as one list in run order.

    One `TaskResult` per goal: the node's output (a `FailedGoalOutput` for a
    goal that failed or was skipped), stamped with its instruction and holding
    the `preview` books it kept, plus what it cost. The executor sorts sources
    from failures itself.

    A `WorkflowInput`, not a `NodeInput`: a pipeline step has no planner
    instruction. What was asked is `ctx.user_message`, which this stage reads
    directly because it answers the turn rather than a goal.
    """

    results: list[TaskResult] = Field(default_factory=list)


class TextBlock(BaseModel):
    type: Literal["text"]
    text: str = Field(description="Markdown the user reads. Never a handle.")


class SourceBlock(BaseModel):
    type: Literal["source"]
    refs: list[str] = Field(
        description="Handles like `1.2` of the books the text just before talks about."
    )


class GenerationResult(BaseModel):
    """The reply as the writer fills it in: prose, each part followed by the
    cards it talks about.

    An internal tool like a slice's `*Args` — never seen by the planner, so no
    `node_type`. The wrapper exists because a tool's root must be an object.
    """

    blocks: list[TextBlock | SourceBlock]


class RecommendationsOutput(NodeWorkflowOutput):
    """The turn's reply.

    `blocks` is kept even though it already reached the browser: the stream is
    not readable back, and this is what lands in `chat_runs` and what a later
    conversational turn would read.

    Every field needs a default; the workflow builds its output empty.
    """

    render_evidence: str | None = None
    blocks: list[TextBlock | SourceBlock] = Field(default_factory=list)
    num_books_shown: int = 0

    def to_summary(self) -> dict[str, Any]:
        return {
            "num_books_shown": self.num_books_shown,
            "num_chars": sum(
                len(b.text) for b in self.blocks if isinstance(b, TextBlock)
            ),
        }
