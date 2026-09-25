"""What triage exposes to the layers around it: how the message split up, and
the plan when there is one.

`tools.py` is what the *LLM* fills in; this is what the orchestrator and the
run recorder read back. `QueryPortion` and `TriageVerdict` sit here rather
than there for the same reason `SystemGoal` sits in planjane's `external.py`:
the decomposition emits them, and then they travel — onto `TriageOutput`, into
every `chat_runs` row.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.domains.base_workflow import NodeWorkflowOutput
from app.domains.planjane import ExecutionOrder, PlanJaneOutput


class TriageVerdict(str, Enum):
    """What one portion of the message is. Only `IN_DOMAIN` portions reach the
    planner; a message with none is answered with a fixed reply."""

    IN_DOMAIN = "in_domain"
    SMALL_TALK = "small_talk"
    OUT_OF_SCOPE = "out_of_scope"
    SECURITY = "security"
    GIBBERISH = "gibberish"


class QueryPortion(BaseModel):
    """One ask or remark from the message, copied exactly as the user wrote
    it — no corrections."""

    # Unbounded on purpose: the route already caps a message at 2,000
    # characters, and a clipped portion would change what the planner is asked.
    text: str = Field(
        ...,
        min_length=1,
        json_schema_extra={"example": "find me books like Dune"},
    )
    verdict: TriageVerdict


# NOTE: this is okay for now
# this should store conversation summary, failed tasks, internal summary message
# for llm — maybe also referenced books or things from processing the steps
class TriageOutput(NodeWorkflowOutput):
    session_id: str | None = None

    # How the message split up. None when a cached plan was replayed, or the
    # decomposition itself failed and the whole message went to the planner.
    portions: list[QueryPortion] | None = None

    # The plan, when triage produced one. None means the turn was handled
    # without planning, or failed before the planner returned.
    #
    # The name is a *serialized* path: evals/planjane/report_system_goals.py,
    # the cache files and every chat_runs row all key on `parse_result`.
    # Renaming it to `plan` means changing all four in lockstep.
    parse_result: PlanJaneOutput | None = None

    def to_summary(self) -> dict[str, Any]:
        return {
            "portions": self.portions,
            "plan": self.parse_result.to_summary() if self.parse_result else None,
        }

    @property
    def diagram(self) -> str | None:
        """The plan's Mermaid diagram, rendered by PlanJane. Surfaced here
        because `chat_runs.mermaid` is promoted out of this envelope and the
        review page reads it."""
        return self.parse_result.diagram if self.parse_result else None

    def execution_order(self) -> ExecutionOrder | None:
        if not self.parse_result:
            return None
        return self.parse_result.execution_order()

    def accepted_goals_ids(self) -> list[str] | None:
        if not self.parse_result:
            return None
        return self.parse_result.accepted_goals_ids()
