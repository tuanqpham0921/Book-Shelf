import logging

from dataclasses import dataclass

from app.common.prompt_loader import load_prompt, format_prompt

from app.common.sse_stream import SSEStream
from clients import OpenAIParserRequest

from app.common.workflow import UserFacingBaseWorkflow, UserFacingOutput
from app.common.messages import UserMessage
from clients.openai_client import OpenAIClient

from typing import Optional
from pydantic import BaseModel, Field, field_validator
from app.common.messages import AssistantMessage, BaseMessage
from app.domains.registry import format_node_type_catalog
from typing import Annotated
from pydantic import PrivateAttr
import uuid
from clients.openai_requests import OpenAIChatRequest
from app.orchestration.planner.request_context import SystemGoal, InitialParseRequest
from app.orchestration.planner.request_context import MAX_SYSTEM_GOALS
from dataclasses import field

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AcceptedSystemGoal:
    id: str
    goal: SystemGoal


@dataclass(slots=True)
class RejectedSystemGoal(AcceptedSystemGoal):
    reason: str


@dataclass(slots=True)
class InitialParseOutput(UserFacingOutput):
    accepted_system_goals: list[AcceptedSystemGoal] = field(default_factory=list)
    rejected_system_goals: list[RejectedSystemGoal] = field(default_factory=list)
    
    small_talk: Optional[str] = field(default=None)
    out_of_scope: Optional[str] = field(default=None)
    reasoning: Optional[str] = field(default=None)

    def to_summary(self) -> dict[str, str | bool | None]:
        return {
            "total_system_goals": len(self.accepted_system_goals),
            "num_rejected_system": len(self.rejected_system_goals),
            "num_accepted_system": len(self.accepted_system_goals),
            "system_goals": [goal.description for goal in self.accepted_system_goals],
            "rejected_system_goals": [
                goal.goal.description for goal in self.rejected_system_goals
            ],
            "accepted_system_goals": [
                goal.goal.description for goal in self.accepted_system_goals
            ],
            "small_talk": self.small_talk,
            "out_of_scope": self.out_of_scope,
            "reasoning": self.reasoning,
        }

    def to_llm_messages(self) -> list[AssistantMessage]:
        import json
        return [
            AssistantMessage(
                content=json.dumps(
                    {
                        "small_talk": self.small_talk,
                        "out_of_scope": self.out_of_scope,
                        "rejected_system_goals": [
                            (g.goal, g.reason)
                            for g in self.rejected_system_goals
                        ],
                        "continue_pipeline": len(self.accepted_system_goals) > 0,
                        "reasoning": self.reasoning,
                    }
                )
            )
        ]


class InitialParseWorkflow(UserFacingBaseWorkflow[InitialParseOutput]):
    success_message = "Initial parse completed successfully"
    failure_message = "Initial parse failed"
    ui_loading_message = "Thinking..."

    _SYSTEM_PROMPT_PATH = "orchestration/planner/prompts/0_initial_system.txt"
    _USER_PROMPT_PATH = "orchestration/planner/prompts/1_initial_parse_response.txt"

    tool_models = [InitialParseRequest]

    def __init__(
        self, sse_stream: SSEStream, user_message: UserMessage, llm_client: OpenAIClient
    ):
        super().__init__(
            llm_client=llm_client,
            sse_stream=sse_stream,
            output_type=InitialParseOutput,
        )
        self.user_message = user_message

    async def run(self) -> None:
        await self.sse_stream.send_ui_loading(self.ui_loading_message)

        system_prompt = format_prompt(
            prompt_path=self._SYSTEM_PROMPT_PATH,
            TOOLS_NAME_DESCRIPTION=format_node_type_catalog(),
        )
        req = OpenAIParserRequest(
            prompt=system_prompt,
            messages=[self.user_message],
            tool_models=self.tool_models,
        )
        assistant_msg = await self.run_llm_call(req)
        tool_call = assistant_msg.tool_calls[0]
        parse_result = tool_call.function.parsed_arguments

        self.process_parse_result(parse_result)        
        await self.finalize_result()
        
        
    async def finalize_result(self) -> None:
        self.output.summary = "Placeholder summary"
        super().finalize_result(
            ok=bool(self.output.accepted_system_goals)
        )
        await self.generate_user_response()
        
    async def generate_user_response(self) -> None:
        to_llm_messages = self.output.to_llm_messages()
        await self.run_llm_call(
            req=OpenAIChatRequest(
                prompt=load_prompt(prompt_path=self._USER_PROMPT_PATH),
                messages=to_llm_messages,
                sse_stream=self.sse_stream,
                temperature=0.7,
                top_p=1.0,
            ),
        )
        print(f"To LLM messages: {to_llm_messages}")
        
        if self.output.accepted_system_goals:
            await self.sse_stream.send_chars("\n\n# System Goals:\n")
            for system_goal in self.output.accepted_system_goals:
                await self.sse_stream.send_chars(f"- {system_goal.goal.description}\n")

    def process_parse_result(
        self, parse_result: InitialParseRequest, confident_tuning: float = 0.5
    ) -> None:
        if (
            len(parse_result.system_goals) == 0
            and not parse_result.small_talk
            and not parse_result.out_of_scope
        ):
            logger.warning("Nothing was classified in the initial parse")
            self.output.ok = False
            self.output.reasoning = "Nothing was classified in the initial parse"
            return
        
        self.output.small_talk = parse_result.small_talk
        self.output.out_of_scope = parse_result.out_of_scope
        self.output.reasoning = parse_result.reasoning

        count = 1
        for goal in parse_result.system_goals:
            if goal.confidence >= confident_tuning and count < MAX_SYSTEM_GOALS:
                accepted_goal = AcceptedSystemGoal(
                    id=f"goal_{count}",
                    goal=goal,
                )
                self.output.accepted_system_goals.append(accepted_goal)
            else:
                reason = (
                    f"Rejected: confidence too low ({goal.confidence})"
                    if goal.confidence < confident_tuning
                    else f"Rejected: exceeded max goals ({MAX_SYSTEM_GOALS})"
                )
                rejected_goal = RejectedSystemGoal(
                    id=f"goal_{count}",
                    goal=goal,
                    reason=reason,
                )
                self.output.rejected_system_goals.append(rejected_goal)
            count += 1
            
        
