"""The first thing a turn does with the user's message: check it.

Every message arrives from the route as an `UserMessage`. One
cheap call decides whether it may go any further: no security threat, no
harmful content, not gibberish. Only a message that passes becomes the
`UserMessage` the rest of the turn reads; one that fails gets a fixed reply
from here and the turn ends.

A `@task` rather than a workflow, like `start_session_turn`: `Orchestrator.run`
attaches its envelope by hand, so the check and its spend are a step on the
turn's trace either way.
"""

from airglider import current_parent, task
from app.common.prompt_loader import load_prompt
from app.common.request_context import RequestContext
from clients import OpenAIParserRequest
from clients.messages import UserMessage

from .tools import UserMsgValidation

VALIDATE_PROMPT_PATH = "orchestration/validation/prompts/validate_message.txt"

# A few sentences of justification and three flags. At reasoning effort
# "none" nothing hidden counts against this cap, so all of it is the tool
# call. Running out means no tool call, and the turn stops.
MAX_COMPLETION_TOKENS = 500

# Fixed text rather than anything the model writes, so nothing a prompt
# injection steers ever reaches the user.
HARMFUL_REPLY = (
    "Your input has been flagged for security review.\n"
    "For now, I reject these messages right away, until a more "
    "sophisticated review is in place."
)
INCOHERENT_REPLY = (
    "Sorry, I can't understand what you're asking for.\n"
    "Could you be more specific?"
)


def build_validation_request(content: str) -> OpenAIParserRequest:
    """Ask a cheap model to check the message.

    It runs ahead of every turn, so it is kept fast: gpt-6-luna at reasoning
    effort "none" (2026-09-26, replacing gpt-5-mini at minimal) — the tool's
    `reasoning` field is written out before the flags instead. The raw
    message goes out as a user turn here and nowhere else.
    """
    return OpenAIParserRequest(
        prompt=load_prompt(prompt_path=VALIDATE_PROMPT_PATH),
        model="gpt-6-luna",
        reasoning_effort="none",
        messages=[UserMessage(content=content)],
        tool_models=[UserMsgValidation],
        max_completion_tokens=MAX_COMPLETION_TOKENS,
    )


def refusal_for(validation: UserMsgValidation) -> str | None:
    """The reply a failed check gets, or None when the message passes. The
    order is the priority: a message flagged both harmful and gibberish is
    refused as harmful."""
    if validation.security_issue or validation.harmful_content:
        return HARMFUL_REPLY
    if validation.gibberish_or_incoherent:
        return INCOHERENT_REPLY
    return None


@task
async def validate_user_message(request_context: RequestContext) -> UserMsgValidation:
    """Check the turn's message. Raises when the model returns no verdict, so
    `run`'s unwrap stops the turn: nothing unchecked goes further."""
    request = build_validation_request(request_context.user_message.content)
    msg = await request_context.llm_client.execute(request)
    # a @task promotes usage only off its return value, and this one returns
    # the parsed arguments, so the call's spend is stamped here
    current_parent().token_usage += msg.token_usage
    if not msg.tool_calls:
        raise ValueError("LLM response contained no tool calls")
    return msg.tool_calls[0].function.parsed_arguments
