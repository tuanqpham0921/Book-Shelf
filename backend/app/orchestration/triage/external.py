"""What triage exposes to the layers around it: the plan when there is one.

`tools.py` is what the *LLM* fills in; this is what the orchestrator and the
run recorder read back.
"""

from typing import Any

from app.domains.base_workflow import NodeWorkflowOutput
from app.domains.planjane import ExecutionOrder, PlanJaneOutput


# NOTE: this is okay for now
# this should store conversation summary, failed tasks, internal summary message
# for llm — maybe also referenced books or things from processing the steps
class TriageOutput(NodeWorkflowOutput):
    session_id: str | None = None

    # The plan, when triage produced one. None means the turn was handled
    # without planning, or failed before the planner returned.
    #
    # The name is a *serialized* path: evals/planjane/report_system_goals.py,
    # the cache files and every chat_runs row all key on `parse_result`.
    # Renaming it to `plan` means changing all four in lockstep.
    parse_result: PlanJaneOutput | None = None

    def to_summary(self) -> dict[str, Any]:
        return {
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
