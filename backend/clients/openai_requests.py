import logging
from typing import Any

from .base import BaseLLMRequest

from config import settings
from config.constants import OpenAIConstants
from clients.messages import AssistantMessage, SystemMessage, ToolMessage
from openai import pydantic_function_tool
from openai.types.chat import ChatCompletionFunctionToolParam
from pydantic import model_validator, Field
from typing import Annotated

logger = logging.getLogger(__name__)

TEMPERATURE = 0.3
TOP_P = 0.8
SEED = 42
REASONING_EFFORT = "low"

# The two model families, and what each one takes. A reasoning model is told
# how hard to think; everything else is told how to sample. Sending the wrong
# set is not a soft error at the API, so the split is enforced below rather
# than left to whoever writes the next `build_*_request`.
NOT_REASONING_MODEL_PREFIX = "gpt-4"
SAMPLING_FIELDS = frozenset({"temperature", "top_p", "seed"})

# The app's own list, not the SDK's: `openai.types.shared.ReasoningEffort`
# omits "none", which gpt-5.6 accepts and the planner uses. Widen this when a
# model gains a level — an unknown value is a typo far more often than a
# feature, and the API rejects it either way.
REASONING_EFFORTS = frozenset({"none", "minimal", "low", "medium", "high"})


class OpenAIBaseRequest(BaseLLMRequest):
    model: str = settings.openai.BASE_MODEL
    temperature: float | None = Field(default=TEMPERATURE, ge=0.0, le=2.0)
    top_p: float | None = Field(default=TOP_P, ge=0.0, le=1.0)
    seed: int | None = SEED
    reasoning_effort: str | None = REASONING_EFFORT

    # The app-wide guard is both the default and the ceiling: a node may ask
    # for less when it knows its output is small, and asking for more is a
    # misconfiguration rather than a choice.
    max_completion_tokens: int = Field(
        default=OpenAIConstants.MAX_DEFAULT_COMPLETION,
        gt=0,
        le=OpenAIConstants.MAX_DEFAULT_COMPLETION,
    )

    @property
    def is_reasoning_model(self) -> bool:
        """Which family this request is for. One definition — the validator
        below and `base_payload` both ask it, and they must agree."""
        return (not self.model.startswith(NOT_REASONING_MODEL_PREFIX))

    @model_validator(mode="after")
    def check_tool_message_linkage(self) -> "OpenAIBaseRequest":
        assistant_tool_call_ids = {
            tc.id
            for m in self.messages
            if isinstance(m, AssistantMessage) and m.tool_calls
            for tc in m.tool_calls
        }
        tool_message_ids = {
            m.tool_call_id for m in self.messages if isinstance(m, ToolMessage)
        }

        orphaned = tool_message_ids - assistant_tool_call_ids
        if orphaned:
            raise ValueError(f"ToolMessage has no matching assistant tool_call: {orphaned}")

        unanswered = assistant_tool_call_ids - tool_message_ids
        if unanswered:
            raise ValueError(f"Assistant tool_call has no ToolMessage reply: {unanswered}")

        return self
    
    @model_validator(mode="after")
    def check_model_family_settings(self) -> "OpenAIBaseRequest":
        """Refuse a setting the chosen model does not take, then clear the
        other family's defaults.

        The distinction that makes this usable is *explicitly set* vs. left at
        the class default: every one of these fields has a default, so raising
        on a mere value would reject every request. `model_fields_set` is what
        the caller actually passed, so a `build_*_request` that names a field
        its model ignores fails here — at construction, naming the field and
        the model — instead of having the value silently dropped on the way to
        the payload.

        Copied, because assigning below adds those names to the live set.
        """
        configured = set(self.model_fields_set)

        if self.is_reasoning_model:
            ignored = sorted(SAMPLING_FIELDS & configured)
            if ignored:
                raise ValueError(
                    f"{self.model} is a reasoning model and ignores "
                    f"{', '.join(ignored)} — set reasoning_effort instead"
                )
            if self.reasoning_effort not in REASONING_EFFORTS:
                raise ValueError(
                    f"reasoning_effort={self.reasoning_effort!r} is not one of "
                    f"{', '.join(sorted(REASONING_EFFORTS))}"
                )
            self.temperature = None
            self.top_p = None
            self.seed = None
        else:
            if "reasoning_effort" in configured:
                raise ValueError(
                    f"{self.model} is not a reasoning model and ignores "
                    f"reasoning_effort — set temperature, top_p or seed instead"
                )
            self.reasoning_effort = None

        return self


    def to_summary(self) -> dict[str, Any]:
        """Adds the two OpenAI-specific things a trace is read for: the
        reasoning effort a cost line is explained by, and *which* schema a
        parser call was filling in.

        `tool_models` is reached by `getattr` because only the parser and tool
        subclasses declare it — one override covering every request beats three
        that differ by a line.
        """
        summary = super().to_summary()
        summary["reasoning_effort"] = self.reasoning_effort
        tool_models = getattr(self, "tool_models", None)
        if tool_models:
            summary["tools"] = [model.__name__ for model in tool_models]
        return summary

    def to_messages_payload(self) -> list[dict[str, Any]]:
        messages = []
        if self.prompt:
            messages.append(SystemMessage(content=self.prompt).model_dump())
        messages.extend([m.to_openai_dict() for m in self.messages])
        return messages

    def base_payload(self) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": self.to_messages_payload(),
            "stream_options": {"include_usage": True},
            "max_completion_tokens": self.max_completion_tokens,
        }

        if self.is_reasoning_model:
            payload["reasoning_effort"] = self.reasoning_effort
        else:
            payload["temperature"] = self.temperature
            payload["top_p"] = self.top_p
            payload["seed"] = self.seed

        return payload

    def to_payload(self) -> dict[str, Any]:
        return self.base_payload()


class OpenAIParserRequest(OpenAIBaseRequest):
    """Support only one tool model for parsing 1 request"""

    tool_models: Annotated[list[type], Field(min_length=1, max_length=1)]
    tool_override: dict | None = None
    # A node class docstring is *selection* prose — it exists so the planner can
    # choose between tools. When tool_choice already pins the one tool, sending
    # it is noise. Field descriptions are unaffected: those are what actually
    # guide the argument fill.
    include_tool_description: bool = True

    def to_payload(self) -> dict[str, Any]:
        payload = self.base_payload()

        payload["tools"] = (
            [self.to_function_tools()]
            if not self.tool_override
            else [self.tool_override]
        )
        payload["tool_choice"] = {
            "type": "function",
            "function": {"name": self.tool_models[0].__name__},
        }
        return payload

    def to_function_tools(self) -> ChatCompletionFunctionToolParam:
        tool_name = self.tool_models[0].__name__
        tool = pydantic_function_tool(
            self.tool_models[0],
            name=tool_name,
        )
        if not self.include_tool_description:
            # Mutate in place: tool["function"] is a PydanticFunctionTool (a dict
            # subclass carrying .model) and the openai lib keys auto-parsing off
            # that type. Replacing the dict would silently downgrade
            # parsed_arguments to a raw dict.
            tool["function"].pop("description", None)
        return tool


class OpenAIChatRequest(OpenAIBaseRequest):
    """Support only sse stream no tool choice"""

    @model_validator(mode="after")
    def check_sse_stream(self) -> "OpenAIChatRequest":
        if not self.sse_stream:
            raise ValueError("Usage error: sse_stream must be provided")
        return self
