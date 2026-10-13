"""`TriageOutput`, what the orchestrator and run recorder read back: the plan,
and the project facts when the router looked them up itself."""

from typing import Any

from app.domains.base_workflow import NodeWorkflowOutput
from app.domains.planjane import PlanJaneOutput
from app.domains.project.find_project_info import ProjectInfoOutput


# TODO: carry what a later turn needs (a conversation summary, failed tasks,
# referenced books) once conversations are multi-turn
class TriageOutput(NodeWorkflowOutput):
    session_id: str | None = None

    # The plan, when triage produced one. None means the turn was handled
    # without planning, or failed before the planner returned.
    #
    # The name is a *serialized* path: evals/planjane/report_system_goals.py,
    # the cache files and every chat_runs row all key on `parse_result`.
    # Renaming it to `plan` means changing all four in lockstep.
    parse_result: PlanJaneOutput | None = None

    # The facts the router asked for with `ProjectInfoArgs`, looked up without
    # planning. The orchestrator writes the reply from them together with
    # whatever the plan found — or from them alone, when there is no plan.
    project_info: ProjectInfoOutput | None = None

    def to_summary(self) -> dict[str, Any]:
        return {
            "plan": self.parse_result.to_summary() if self.parse_result else None,
            "project_info": (
                self.project_info.to_summary() if self.project_info else None
            ),
        }

    @property
    def diagram(self) -> str | None:
        """The plan's Mermaid diagram, rendered by PlanJane. Surfaced here
        because `chat_runs.mermaid` is promoted out of this envelope and the
        review page reads it."""
        return self.parse_result.diagram if self.parse_result else None
