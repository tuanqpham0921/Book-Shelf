"""The first thing a turn does with the user's message: check it.

Every message arrives from the route as an `UnvalidatedUserMessage`. One
cheap call decides whether it may go any further: written in a language the
app answers in, coherent, not asking for harm, not trying to steer the model.
Only a message that passes becomes the `UserMessage` the rest of the turn
reads; one that fails gets a fixed reply from here and the turn ends.

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

# The catalog and every reply are English, so an answer in anything else
# would be the planner guessing. ISO 639-1, as the tool reports it.
SUPPORTED_LANGUAGES = frozenset({"en"})

# Four short fields, plus headroom for the reasoning tokens that count against
# this cap. Running out means no tool call, and the turn stops.
MAX_COMPLETION_TOKENS = 500

# Fixed text rather than anything the model writes, so nothing a prompt
# injection steers ever reaches the user.
HARMFUL_REPLY = (
    "I can't help with that. I can help you find books, authors, or your next read."
)
CODE_REPLY = (
    "I can't take code in messages. Ask about books instead, for example: "
    '"books about Python".'
)
INCOHERENT_REPLY = (
    "I couldn't make sense of that. Please be more sepcific"
)
LANGUAGE_REPLY = (
    "Sorry, I can only chat in English for now"
)


def build_validation_request(content: str) -> OpenAIParserRequest:
    """Ask a cheap model to check the message.

    It runs ahead of every turn, so it is kept fast: minimal effort, about two
    seconds. gpt-5-mini rather than nano, measured 2026-09-25 — nano read a
    Spanish message as English and cost a fraction of a cent less. The raw
    message goes out as a user turn here and nowhere else; the prompt tells
    the model to check it, never follow it.
    """
    return OpenAIParserRequest(
        prompt=load_prompt(prompt_path=VALIDATE_PROMPT_PATH),
        model="gpt-5-mini",
        reasoning_effort="minimal",
        messages=[UserMessage(content=content)],
        tool_models=[UserMsgValidation],
        max_completion_tokens=MAX_COMPLETION_TOKENS,
    )


def refusal_for(validation: UserMsgValidation) -> str | None:
    """The reply a failed check gets, or None when the message passes. The
    order is the priority: a harmful message in Spanish is refused as harmful."""
    if validation.harmful_query or validation.prompt_injection:
        return HARMFUL_REPLY
    if validation.contains_code:
        return CODE_REPLY
    if validation.incoherent:
        return INCOHERENT_REPLY
    if validation.language not in SUPPORTED_LANGUAGES:
        return LANGUAGE_REPLY
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
