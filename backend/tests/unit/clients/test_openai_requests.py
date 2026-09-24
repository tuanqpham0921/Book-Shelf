import pytest
from unittest.mock import MagicMock
from openai.lib._parsing._completions import is_parseable_tool
from pydantic import BaseModel

from clients.messages import AssistantMessage, ToolMessage, UserMessage
from app.common.sse_stream import SSEStream
from pydantic import ValidationError

from clients.openai_requests import (
    REASONING_EFFORT,
    REASONING_EFFORTS,
    SEED,
    TEMPERATURE,
    TOP_P,
    OpenAIBaseRequest,
    OpenAIChatRequest,
    OpenAIParserRequest,
)
from config.constants import OpenAIConstants


USER_MSG = UserMessage(content="hello")


def make_sse_stream():
    return SSEStream()


class ToolA(BaseModel):
    query: str


class ToolB(BaseModel):
    isbn: str


class DocumentedTool(BaseModel):
    """Purpose: pick this tool when the user names a title."""

    query: str


class TestModelFamilySettings:
    """A request must not carry a setting its model ignores.

    The rule is *explicitly set*, not *has a value*: every one of these fields
    has a class default, so the check reads `model_fields_set` and a default
    is cleared rather than refused.
    """

    def test_reasoning_model_clears_sampling_defaults(self):
        req = OpenAIBaseRequest(prompt="p", messages=[USER_MSG], model="gpt-5-nano")
        assert req.temperature is None
        assert req.top_p is None
        assert req.seed is None
        assert req.reasoning_effort == REASONING_EFFORT

    @pytest.mark.parametrize("model", ["gpt-5-nano", "gpt-5.6-luna", "gpt-6-sol"])
    def test_non_gpt4_models_are_reasoning_models(self, model):
        req = OpenAIBaseRequest(prompt="p", messages=[USER_MSG], model=model)
        assert req.is_reasoning_model

    def test_sampling_model_clears_reasoning_default(self):
        req = OpenAIBaseRequest(prompt="p", messages=[USER_MSG], model="gpt-4.1-mini")
        assert req.reasoning_effort is None
        assert req.temperature == TEMPERATURE

    @pytest.mark.parametrize("field,value", [("temperature", 0.3), ("top_p", 0.5), ("seed", 1)])
    def test_reasoning_model_refuses_sampling_settings(self, field, value):
        with pytest.raises(ValidationError, match="ignores"):
            OpenAIBaseRequest(
                prompt="p", messages=[USER_MSG], model="gpt-5-nano", **{field: value}
            )

    def test_sampling_model_refuses_reasoning_effort(self):
        with pytest.raises(ValidationError, match="reasoning_effort"):
            OpenAIBaseRequest(
                prompt="p", messages=[USER_MSG], model="gpt-4.1-mini", reasoning_effort="low"
            )

    @pytest.mark.parametrize("effort", sorted(REASONING_EFFORTS))
    def test_every_known_effort_is_accepted(self, effort):
        req = OpenAIBaseRequest(
            prompt="p", messages=[USER_MSG], model="gpt-5-nano", reasoning_effort=effort
        )
        assert req.base_payload()["reasoning_effort"] == effort

    def test_unknown_effort_is_refused(self):
        # the typo case: "lo" would otherwise travel to the API
        with pytest.raises(ValidationError, match="is not one of"):
            OpenAIBaseRequest(
                prompt="p", messages=[USER_MSG], model="gpt-5-nano", reasoning_effort="lo"
            )


class TestCompletionCapBounds:
    """The app-wide guard is both the default and the ceiling, so a node's
    only move is downward."""

    def test_the_default_is_the_app_wide_guard(self):
        req = OpenAIBaseRequest(prompt="p", messages=[USER_MSG])
        assert req.max_completion_tokens == OpenAIConstants.MAX_DEFAULT_COMPLETION

    def test_a_node_may_lower_its_cap(self):
        req = OpenAIBaseRequest(
            prompt="p", messages=[USER_MSG], max_completion_tokens=500
        )
        assert req.max_completion_tokens == 500

    def test_above_the_ceiling_is_refused(self):
        with pytest.raises(ValidationError, match="less than or equal"):
            OpenAIBaseRequest(
                prompt="p",
                messages=[USER_MSG],
                max_completion_tokens=OpenAIConstants.MAX_DEFAULT_COMPLETION + 1,
            )

    @pytest.mark.parametrize("bad", [0, -1])
    def test_non_positive_cap_is_refused(self, bad):
        with pytest.raises(ValidationError, match="greater than"):
            OpenAIBaseRequest(prompt="p", messages=[USER_MSG], max_completion_tokens=bad)

    @pytest.mark.parametrize("field,bad", [("temperature", 2.1), ("top_p", 1.1)])
    def test_sampling_settings_stay_in_range(self, field, bad):
        with pytest.raises(ValidationError):
            OpenAIBaseRequest(
                prompt="p", messages=[USER_MSG], model="gpt-4.1-mini", **{field: bad}
            )


class TestOpenAIBaseRequest:
    def test_defaults(self):
        req = OpenAIBaseRequest(prompt="p", messages=[USER_MSG])
        assert req.temperature == TEMPERATURE
        assert req.top_p == TOP_P
        assert req.seed == SEED

    def test_base_payload_keys(self):
        req = OpenAIBaseRequest(prompt="p", messages=[USER_MSG])
        payload = req.base_payload()
        assert set(payload.keys()) == {
            "model",
            "messages",
            "temperature",
            "top_p",
            "seed",
            "stream_options",
            "max_completion_tokens",
        }

    def test_base_payload_includes_stream_options(self):
        req = OpenAIBaseRequest(prompt="p", messages=[USER_MSG])
        assert req.base_payload()["stream_options"] == {"include_usage": True}

    def test_to_messages_payload_includes_system_message(self):
        req = OpenAIBaseRequest(prompt="be helpful", messages=[USER_MSG])
        msgs = req.to_messages_payload()
        roles = [m["role"] for m in msgs]
        assert "system" in roles
        assert "user" in roles

    def test_to_messages_payload_no_prompt(self):
        req = OpenAIBaseRequest(prompt="", messages=[USER_MSG])
        msgs = req.to_messages_payload()
        assert all(m["role"] != "system" for m in msgs)

    def test_to_payload_returns_base_payload(self):
        req = OpenAIBaseRequest(prompt="p", messages=[USER_MSG])
        assert req.to_payload() == req.base_payload()

    def test_tool_message_without_assistant_tool_call_raises(self):
        tool_msg = ToolMessage(name="search", tool_call_id="tc_1", content="result")
        with pytest.raises(ValueError, match="no matching assistant tool_call"):
            OpenAIBaseRequest(prompt="p", messages=[USER_MSG, tool_msg])

    def test_unanswered_assistant_tool_call_raises(self):
        assistant_msg = AssistantMessage.model_construct(tool_calls=[MagicMock(id="tc_1")])
        with pytest.raises(ValueError, match="no ToolMessage reply"):
            OpenAIBaseRequest(prompt="p", messages=[USER_MSG, assistant_msg])

    def test_matched_tool_call_and_reply_passes(self):
        assistant_msg = AssistantMessage.model_construct(tool_calls=[MagicMock(id="tc_1")])
        tool_msg = ToolMessage(name="search", tool_call_id="tc_1", content="result")
        req = OpenAIBaseRequest(prompt="p", messages=[USER_MSG, assistant_msg, tool_msg])
        payload = req.to_messages_payload()
        assert len(payload) == 4  # system + user + assistant + tool


class TestOpenAIParserRequest:
    def test_accepts_exactly_one_tool_model(self):
        req = OpenAIParserRequest(prompt="p", messages=[USER_MSG], tool_models=[ToolA])
        assert req.tool_models == [ToolA]

    def test_rejects_empty_tool_models(self):
        with pytest.raises(Exception):
            OpenAIParserRequest(prompt="p", messages=[USER_MSG], tool_models=[])

    def test_rejects_more_than_one_tool_model(self):
        with pytest.raises(Exception):
            OpenAIParserRequest(prompt="p", messages=[USER_MSG], tool_models=[ToolA, ToolB])

    def test_to_payload_has_tools_and_tool_choice(self):
        req = OpenAIParserRequest(prompt="p", messages=[USER_MSG], tool_models=[ToolA])
        payload = req.to_payload()
        assert "tools" in payload
        assert payload["tool_choice"]["function"]["name"] == "ToolA"

    def test_docstring_is_sent_as_description_by_default(self):
        req = OpenAIParserRequest(
            prompt="p", messages=[USER_MSG], tool_models=[DocumentedTool]
        )
        tool = req.to_function_tools()
        assert tool["function"]["description"] == DocumentedTool.__doc__

    def test_description_dropped_when_disabled(self):
        req = OpenAIParserRequest(
            prompt="p",
            messages=[USER_MSG],
            tool_models=[DocumentedTool],
            include_tool_description=False,
        )
        tool = req.to_function_tools()
        assert "description" not in tool["function"]
        # dropping it must not cost us auto-parsing: the openai lib keys that off
        # tool["function"] still being a PydanticFunctionTool carrying .model
        assert is_parseable_tool(tool)
        assert tool["function"].model is DocumentedTool

    def test_to_payload_uses_tool_override(self):
        override = {"type": "function", "function": {"name": "custom"}}
        req = OpenAIParserRequest(
            prompt="p", messages=[USER_MSG], tool_models=[ToolA], tool_override=override
        )
        payload = req.to_payload()
        assert payload["tools"] == [override]

    def test_to_payload_sends_max_completion_tokens(self):
        # the live path: every parse in the app goes through this class, and
        # the cap used to be dropped here silently
        req = OpenAIParserRequest(prompt="p", messages=[USER_MSG], tool_models=[ToolA])
        assert (
            req.to_payload()["max_completion_tokens"]
            == OpenAIConstants.MAX_DEFAULT_COMPLETION
        )

    def test_to_payload_honors_a_lowered_cap(self):
        # how a node tightens the guard when it knows its output is small
        req = OpenAIParserRequest(
            prompt="p",
            messages=[USER_MSG],
            tool_models=[ToolA],
            max_completion_tokens=500,
        )
        assert req.to_payload()["max_completion_tokens"] == 500


class TestOpenAIChatRequest:
    def test_requires_sse_stream(self):
        with pytest.raises(ValueError, match="sse_stream"):
            OpenAIChatRequest(prompt="p", messages=[USER_MSG])

    def test_accepts_sse_stream(self):
        req = OpenAIChatRequest(prompt="p", messages=[USER_MSG], sse_stream=make_sse_stream())
        assert req.sse_stream is not None

    def test_to_payload_has_max_completion_tokens(self):
        # inherited from the base now; the chat class no longer declares a
        # second field of its own
        req = OpenAIChatRequest(prompt="p", messages=[USER_MSG], sse_stream=make_sse_stream())
        assert (
            req.to_payload()["max_completion_tokens"]
            == OpenAIConstants.MAX_DEFAULT_COMPLETION
        )


