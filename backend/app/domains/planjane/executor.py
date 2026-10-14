"""PlanJane's executor: parse the message into goals, sort them, draw the plan."""

import logging

from clients.messages import UserMessage
from app.common.prompt_loader import format_prompt
from app.domains.base_workflow import AppWorkflow
from app.domains.node_input import NodeInput, ParsedInput
from app.registry import REGISTRY
from clients import OpenAIParserRequest

from .dial import get_goals_mermaid_diagram
from .external import PlanJaneOutput, SystemGoal
from .tools import MAX_SYSTEM_GOALS, GoalParseRequest

logger = logging.getLogger(__name__)

# The planner is reachable from both ends: the user's text, or the tool schema
# already filled in (see `GoalParseRequest.__call__`).
PlanJaneInput = NodeInput | ParsedInput[GoalParseRequest]

GOAL_GENERATOR_PROMPT_PATH = "domains/planjane/prompts/0_goal_generator.txt"

# A maximal plan — MAX_SYSTEM_GOALS (10) goals with every string at its bound —
# serializes to ~1,341 tokens, so this is the schema's own worst case plus
# margin. Raise it with MAX_SYSTEM_GOALS or MAX_INSTRUCTION_LENGTH.
MAX_COMPLETION_TOKENS = 2_000

# A goal below this confidence is refused; exactly at it is accepted.
MIN_GOAL_CONFIDENCE = 0.5


class PlanJaneExecutor(AppWorkflow[PlanJaneOutput]):
    description = "Plans the steps to answer you"

    ui_loading_message = "thinking..."

    async def run(self, node_input: PlanJaneInput) -> None:
        """Two ways in, one body.

        From natural language (`NodeInput`) the planner makes the tool call
        itself; handed an already-filled `GoalParseRequest` it skips to the
        processing. Everything after the branch is shared, which is the point —
        the tool schema can be exposed and called directly without a second
        implementation of what happens to the goals.
        """
        await self.sse_stream.send_ui_loading(self.ui_loading_message)

        # 1. parse the message into goals — or take them already parsed
        if isinstance(node_input, NodeInput):
            parse_result: GoalParseRequest = await self.run_llm_args_parse(
                build_goal_parse_request(node_input.instruction)
            )
        else:
            # already validated as GoalParseRequest by the field's annotation
            parse_result = node_input.parsed_result

        # 2. sort the goals into accepted / refused / buffered
        self.process_parse_result(parse_result)

        # 3. show the plan — the diagram is the plan rendered
        # TODO: refused goals still reach no reply — only `out_of_scope` does,
        # which the orchestrator hands to the reply stage
        if self.result.accepted_goals:
            await self.send_mermaid(self.result.accepted_goals)

        # 4. finalize — ok is read off the sorted goals
        self.finalize_result()

    def process_parse_result(self, parse_result: GoalParseRequest) -> None:
        """Sort the parsed goals onto the output: refused when unsure or
        unsupported, accepted up to MAX_SYSTEM_GOALS, buffered past it."""
        if len(parse_result.system_goals) == 0 and not parse_result.out_of_scope:
            # raise, not record.ok = False — the envelope stamps the failure
            msg = "Nothing was classified in the initial parse"
            logger.warning(msg)
            raise RuntimeError(msg)

        self.result.out_of_scope = parse_result.out_of_scope

        # overflow goals are valid, just over the limit — same checks, so they
        # can fill capacity freed by refusals or wait in buffer_goals
        for goal in parse_result.system_goals:
            reasons = []
            if goal.confidence < MIN_GOAL_CONFIDENCE:
                reasons.append(f"Rejected: confidence too low ({goal.confidence})")
            if goal.target_node_type not in REGISTRY:
                reasons.append(
                    f"Rejected: target node type not supported ({goal.target_node_type})"
                )
            if reasons or goal._refusal:
                goal.refuse(*reasons)
                self.result.refused_goals.append(goal)
            elif len(self.result.accepted_goals) < MAX_SYSTEM_GOALS:
                self.result.accepted_goals.append(goal)
            else:
                self.result.buffer_goals.append(goal)

    async def send_mermaid(self, system_goals: list[SystemGoal]) -> None:
        """Render the accepted goals as a Mermaid flowchart, stream it and keep
        it on the output. Never raises into the request: a diagram that cannot
        be drawn is noted and skipped."""
        diagram = get_goals_mermaid_diagram(system_goals)
        if not diagram:
            msg = "No Mermaid diagram generated (empty or invalid)"
            logger.warning(msg)
            self.add_details(msg)
            return

        # no heading of its own: the UI titles the plan's section, the same way
        # it titles every step after it
        await self.sse_stream.send_mermaid(diagram)
        self.result.diagram = diagram

    def finalize_result(self) -> None:
        # NOTE: ok means "a plan came out of this turn" — continuation is
        # still decided from accepted_goals, not from ok.
        super().finalize_result(ok=bool(self.result.accepted_goals))


def build_goal_parse_request(query: str) -> OpenAIParserRequest:
    """Ask the LLM to break the message into `GoalParseRequest` goals.

    The one request in the app whose prompt embeds the live tool catalog, and
    the reason accuracy outranks cost on the model choice: the planner sees
    every capability, the cache hit rate is high, and the output is short.
    """
    if not query:
        raise ValueError("No query to plan from")

    return OpenAIParserRequest(
        prompt=format_prompt(
            prompt_path=GOAL_GENERATOR_PROMPT_PATH,
            TOOLS_NAME_DESCRIPTION=REGISTRY.format_catalog(),
        ),
        # the template's path: the catalog it was filled with is not recorded
        prompt_path=GOAL_GENERATOR_PROMPT_PATH,
        model="gpt-6-sol",
        reasoning_effort="none",
        # the input's `instruction`, not `self.user_message`, so a rewritten
        # message (triage's `PlanJane.message`) is what gets parsed
        # NOTE: single-turn only — earlier messages belong here once
        # conversations carry them.
        messages=[UserMessage(content=query)],
        tool_models=[GoalParseRequest],
        max_completion_tokens=MAX_COMPLETION_TOKENS,
    )
