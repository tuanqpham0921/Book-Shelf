"""Triage's flow — what happens to a turn before, and instead of, planning.
`run` is the table of contents; everything else sits where the flow reaches it.

Sits between `Orchestrator` (transport) and `PlanJane` (produce a plan), and
decides whether to plan at all: replay a cached plan, turn the message away
with a fixed reply, or hand the planner the book part of it.

Same reading rule as the slices (domains/README.md): this file is the flow,
with the request builder as a module-level pure function beside it.
`schemas.py` is what the decomposition's LLM fills in, `external.py` is what
the layers around triage read back, `cache.py` is the dev plan replay.

Not in `app/domains/` because it is not a capability — no `NodeSpec` will ever
point at it. A workflow rather than methods on `Orchestrator` because
`Orchestrator` owns no envelope, so a cache hit or a refusal would produce no
step in the trace tree.
"""

import logging

from app.common.prompt_loader import load_prompt
from app.domains.base_workflow import AppWorkflow
from app.domains.node_input import NodeInput
from app.domains.planjane import PlanJaneExecutor
from airglider import task
from clients import OpenAIParserRequest
from clients.messages import UserMessage

from .cache import load_cached_parse_output
from .external import TriageOutput, TriageVerdict
from .schemas import QueryDecomposition

logger = logging.getLogger(__name__)

DECOMPOSE_PROMPT_PATH = "orchestration/triage/prompts/decompose_query.txt"

# The answer copies the message back: at most 2,000 characters (~500 tokens)
# plus a sentence of reasoning. The rest is headroom for reasoning tokens,
# which count against this cap. Running out means no tool call, and the whole
# message goes to the planner.
MAX_COMPLETION_TOKENS = 2_000

# The whole of what a message with no book ask in it gets back — one reply,
# from the first verdict here that any of its portions carries, so the order
# is the priority. Fixed text rather than something the decomposition writes,
# so nothing a prompt injection steers ever reaches the user.
REPLIES: dict[TriageVerdict, str] = {
    TriageVerdict.SECURITY: (
        "I can't help with that. I can help you find books, authors, or your "
        "next read."
    ),
    TriageVerdict.OUT_OF_SCOPE: (
        "That's outside what I can help with. I'm BookShelf, a book "
        "recommender, so ask me about a book, an author, or what to read next."
    ),
    TriageVerdict.SMALL_TALK: (
        "Hi! I'm BookShelf, Tuan's book recommender. I can look up a book by "
        "title or author, find books on a subject or by pages, year or rating, "
        "and suggest books like ones you already love. What would you like to read?"
    ),
    TriageVerdict.GIBBERISH: (
        "I couldn't make sense of that. Could you rephrase it? For example: "
        '"books like Dune".'
    ),
}


def build_decomposition_request(query: str) -> OpenAIParserRequest:
    """Ask a cheap model to split the message into labelled portions.

    Cheap on purpose: it runs ahead of every planned turn, and it only has to
    tell a book ask from everything else — the planner still decides what it
    can actually do. The message goes in as the `UserMessage` it is; the
    prompt tells the model to split it, never follow it.
    """
    return OpenAIParserRequest(
        prompt=load_prompt(prompt_path=DECOMPOSE_PROMPT_PATH),
        model="gpt-5-mini",
        reasoning_effort="low",
        messages=[UserMessage(content=query)],
        tool_models=[QueryDecomposition],
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
                self.result.parse_result = cached
                self.finalize_result(ok=True)
                return

        # 2. split the message before the planner's price is paid. A bare
        # await: a split that failed sends the whole message on — the planner
        # keeps its own trust boundary — rather than stopping the turn
        step = await self.decompose_query(query)
        if step.ok:
            decomposition: QueryDecomposition = step.result
            portions = decomposition.portions
            self.result.portions = portions
            verdicts = ", ".join(portion.verdict.value for portion in portions)
            self.add_details(f"portions: {verdicts} — {decomposition.reasoning}")

            # the planner is asked the book part only; every other portion
            # stops here
            book_ask = [p.text for p in portions if p.verdict is TriageVerdict.IN_DOMAIN]
            if not book_ask:
                # nothing to plan is a handled turn, not a failure: ok, no
                # plan, so the orchestrator skips the runner and the reply
                present = {portion.verdict for portion in portions}
                reply = next(text for v, text in REPLIES.items() if v in present)
                await self.sse_stream.send_chars(reply)
                self.finalize_result(ok=True)
                return
            query = " ".join(book_ask)
        else:
            self.add_details(
                "query decomposition failed; passing the whole message to the planner"
            )

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
    async def decompose_query(self, query: str) -> QueryDecomposition:
        """The decomposition as its own step, so its spend and duration read
        apart from the planner's, and a failure is an envelope `run` can
        inspect rather than an exception that ends the turn."""
        return await self.run_llm_args_parse(build_decomposition_request(query))
