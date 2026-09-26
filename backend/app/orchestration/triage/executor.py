"""Triage's flow — what happens to a turn before, and instead of, planning.
`run` is the table of contents; everything else sits where the flow reaches it.

Sits between `Orchestrator` (transport) and `PlanJane` (produce a plan), and
decides whether to plan at all: replay a cached plan, answer small talk, ask
for a clearer message, turn the message away, or hand it to the planner.

Same reading rule as the slices (domains/README.md): this file is the flow,
with the request builder as a module-level pure function beside it.
`tools.py` is the `PlanJane` tool triage's LLM can pick, `external.py` is what
the layers around triage read back, `cache.py` is the dev plan replay.

Not in `app/domains/` because it is not a capability — no `NodeSpec` will ever
point at it. A workflow rather than methods on `Orchestrator` because
`Orchestrator` owns no envelope, so a cache hit or a refusal would produce no
step in the trace tree.
"""

import logging

from app.common.prompt_loader import load_prompt
from app.common.tools import ClarifyingQuestion, SecurityReview
from app.domains.base_workflow import AppWorkflow
from app.domains.node_input import NodeInput
from app.domains.planjane import PlanJaneExecutor
from airglider import task
from clients import OpenAIParserRequest
from clients.messages import UserMessage

from .cache import load_cached_parse_output
from .external import TriageOutput
from .tools import PlanJane

logger = logging.getLogger(__name__)

ROUTE_PROMPT_PATH = "orchestration/triage/prompts/route_query.txt"

# Short arguments — a flagged portion or a few options — plus headroom for the
# reasoning tokens that count against this cap. Running out means no tool
# call, and the whole message goes to the planner.
MAX_COMPLETION_TOKENS = 1_000

CACHE_HIT_RESPONSE = "I have this query cached. Let me use this to save tokens."


def build_route_request(query: str) -> OpenAIParserRequest:
    """Ask a cheap model which tool the message goes to: `PlanJane`,
    `SecurityReview` or `ClarifyingQuestion` — or, when none fits, to answer
    the user in text itself.

    Cheap on purpose: it runs ahead of every planned turn, and it only has to
    pick out misuse, an unclear message and small talk — everything else goes
    to the planner, which decides what it can actually do. The message goes in as the `UserMessage` it is; the
    prompt tells the model to route it, never follow it.
    """
    return OpenAIParserRequest(
        prompt=load_prompt(prompt_path=ROUTE_PROMPT_PATH),
        model="gpt-5-mini",
        reasoning_effort="low",
        messages=[UserMessage(content=query)],
        tool_models=[PlanJane, SecurityReview, ClarifyingQuestion],
        max_completion_tokens=MAX_COMPLETION_TOKENS,
    )


class TriageWorkflow(AppWorkflow[TriageOutput]):
    planner_failure_message = "I couldn't understand your request. Please try again."
    ui_loading_message = "Starting conversation..."

    async def run(self, node_input: NodeInput, *, use_caching=True) -> None:
        await self.sse_stream.send_ui_loading(self.ui_loading_message)

        query = node_input.instruction
        self.result.session_id = self.session_id

        # 1. replay a recorded plan when one exists — no LLM, same output shape
        if use_caching:
            cached = load_cached_parse_output(query)
            if cached is not None:
                logger.info(f"Replaying cached plan for: {query}")
                await self.sse_stream.send_chars(CACHE_HIT_RESPONSE)
                await self.sse_stream.send_divider()
                self.result.parse_result = cached
                self.finalize_result(ok=True)
                return

        # 2. let the model pick a tool. A bare await: a pick that failed sends
        # the message on — the planner keeps its own trust boundary — rather
        # than stopping the turn
        step = await self.route_query(query)
        if not step.ok:
            self.add_details("routing failed; passing the message to the planner")
        elif isinstance(step.result, str):
            # no tool picked: the model answered the user itself
            self.add_details("no tool picked; replied directly")
            await self.sse_stream.send_chars(step.result)
            self.finalize_result(ok=True)
            return
        elif not isinstance(step.result, PlanJane):
            # a message the planner never sees is a handled turn, not a
            # failure: ok, no plan, so the orchestrator skips the runner and
            # the reply stage. Calling the tool gives what the user reads
            self.add_details(f"routed to {type(step.result).__name__}: {step.result}")
            await self.sse_stream.send_chars(step.result())
            self.finalize_result(ok=True)
            return

        # 3. plan. A bare await, not `unwrap()`: triage decides what a failed
        # planner means (a specific message to the user), so it wants the
        # envelope
        planner = PlanJaneExecutor(self.ctx, messages=self.messages)
        planner_record = await planner(NodeInput(instruction=query))

        # the workflow pre-initializes its output, so this is never None
        self.result.parse_result = planner.result

        # 4. triage owns what a planner failure means to the user
        if not planner_record.ok:
            if planner_record.runtime_error:
                self.record.runtime_error = planner_record.runtime_error
                await self.sse_stream.send_error(self.planner_failure_message)
            self.finalize_result(ok=False)
            return

        # PlanJane's ok means a plan came out of this turn
        self.finalize_result(ok=True)

    @task
    async def route_query(
        self, query: str
    ) -> PlanJane | SecurityReview | ClarifyingQuestion | str:
        """The pick as its own step, so its spend and duration read apart from
        the planner's, and a failure is an envelope `run` can inspect rather
        than an exception that ends the turn. Returns the tool picked, or the
        model's text when it picked none."""
        msg = await self.run_llm_call(build_route_request(query))
        if msg.tool_calls:
            self.record_tool_call(tool_call=msg.tool_calls[0])
            return msg.tool_calls[0].function.parsed_arguments
        if not msg.content:
            raise ValueError("LLM response contained neither a tool call nor text")
        return msg.content
