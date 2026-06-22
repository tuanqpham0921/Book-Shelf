import json
from dataclasses import dataclass
from typing import Any

from app.common.sse_stream import SSEStream
from app.common.messages import UserMessage
from clients.openai_client import OpenAIClient
from app.orchestration.request_context import RequestContext
from app.orchestration.planner.parse_intent import (
    InitialParseWorkflow,
    InitialParseOutput,
)
from app.orchestration.planner.strategy_classification import (
    StrategyClassificationWorkflow,
    StrategyClassificationOutput,
    StrategyClassificationResult,
)
from app.orchestration.planner.task_planner import (
    TaskPlanWorkflow,
    TaskPlanOutput,
    TaskPlan,
)
from app.common.workflow import UserFacingBaseWorkflow, UserFacingOutput
from common.operation import OperationResult
from app.common.prompt_loader import format_prompt
import logging

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class OrchestrationOutput(UserFacingOutput):
    session_id: str | None = None
    parse_result: InitialParseOutput | None = None
    strategy_result: StrategyClassificationResult | None = None
    task_plan: TaskPlan | None = None
    diagram: str | None = None
    
    def to_summary(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parse_result": self.parse_result.to_summary() if self.parse_result else None,
            "strategy_result": self.strategy_result.to_summary() if self.strategy_result else None,
            "task_plan": self.task_plan.to_summary() if self.task_plan else None,
        }

    def _sub_summary(self) -> dict[str, Any]:
        parse_summary = self.parse_result.to_summary() if self.parse_result else None
        strategy_summary = (
            self.strategy_result.to_summary() if self.strategy_result else None
        )
        task_plan_summary = self.task_plan.to_summary() if self.task_plan else None

        return {
            "session_id": self.session_id,
            "parse_result": parse_summary,
            "strategy_result": strategy_summary,
            "task_plan": task_plan_summary,
        }


class ConversationOrchestrator(UserFacingBaseWorkflow[OrchestrationOutput]):
    initial_parse_failure_message = (
        "I couldn't understand your request. Please try again."
    )
    ui_loading_message = "Starting conversation..."
    strategy_classification_failure_message = "I can't find any relevant strategies for your request. Please try again with more specific keywords."
    task_planner_failure_message = "I tried to create a plan, but it was too large or invalid. Try narrowing your request."

    _SUMMARY_PROMPT_PATH = (
        "orchestration/planner/prompts/4_conversation_orchestration_summary.txt"
    )

    def __init__(
        self, sse_stream: SSEStream, user_message: UserMessage, llm_client: OpenAIClient
    ):
        super().__init__(
            llm_client=llm_client,
            sse_stream=sse_stream,
            output_type=OrchestrationOutput,
        )
        self.user_message = user_message

    def add_step(
        self, step: OperationResult[Any], *, raise_on_failure: bool = True
    ) -> OperationResult[Any]:
        step = super().add_step(step, raise_on_failure=raise_on_failure)
        output = step.output

        if isinstance(output, InitialParseOutput):
            self.output.parse_result = output
        elif isinstance(output, StrategyClassificationOutput):
            self.output.strategy_result = output.strategy_result
        elif isinstance(output, TaskPlanOutput):
            self.output.task_plan = output.task_plan

        return step

    async def run(self, request_context: RequestContext) -> None:
        await self.sse_stream.send_ui_loading(self.ui_loading_message)

        self.output.session_id = request_context.session_id
        self.output.chat_messages.append(self.user_message)

        parse_workflow = InitialParseWorkflow(
            self.sse_stream, self.user_message, self.llm_client
        )
        parse_result = await self.run_async_step(
            parse_workflow(), raise_on_failure=False
        )
        if not parse_result.ok:
            if parse_result.run_time_error:
                await self.sse_stream.send_error(self.initial_parse_failure_message)
            self.result.ok = False
            self.result.message = self.initial_parse_failure_message
            return

        await self.sse_stream.send_divider()
        # return
        #------------------------------------------------------------------------------------------------

        system_goals = self.output.parse_result.accepted_goals

        strategy_workflow = StrategyClassificationWorkflow(
            self.sse_stream, self.user_message, self.llm_client
        )
        strategy_result = await self.run_async_step(
            strategy_workflow(system_goals), raise_on_failure=False
        )
        if not strategy_result.ok:
            if strategy_result.run_time_error:
                await self.sse_stream.send_error(
                    self.strategy_classification_failure_message
                )
            self.result.ok = False
            self.result.message = self.strategy_classification_failure_message
            return
        
        #------------------------------------------------------------------------------------------------

        task_workflow = TaskPlanWorkflow(
            self.sse_stream, self.user_message, self.llm_client
        )
        plan_result = await self.run_async_step(
            task_workflow(system_goals, self.output.strategy_result),
            raise_on_failure=False,
        )
        if not plan_result.ok:
            if plan_result.run_time_error:
                await self.sse_stream.send_error(self.task_planner_failure_message)
            self.result.ok = False
            self.result.message = self.task_planner_failure_message
            return

        #------------------------------------------------------------------------------------------------

        self.output.diagram = await self.send_mermaid(
            self.output.task_plan, self.output.strategy_result
        )
        await self.generate_summary()
        #------------------------------------------------------------------------------------------------

        self.result.ok = True
        self.result.message = "Conversation orchestration completed successfully"
        await self.sse_stream.send_divider()

    async def generate_summary(self) -> dict[str, Any]:
        from common.utils import remove_json_empty_values

        sub_summary = remove_json_empty_values(self.output.to_summary())
        prompt = format_prompt(
            self._SUMMARY_PROMPT_PATH,
            sub_summary=json.dumps(sub_summary, indent=2),
        )
        await self.generate_user_response([self.user_message], prompt=prompt)
        return sub_summary

    async def send_mermaid(
        self, task_plan: TaskPlan, strategy_result: StrategyClassificationResult
    ) -> str | None:
        from app.common.mermaid import get_mermaid_diagram

        try:
            diagram = get_mermaid_diagram(
                task_plan, strategy_result.get_accepted_id_to_node()
            )
        except Exception as e:
            logger.warning(f"⚠️ Error generating Mermaid diagram: {e}")
            await self.sse_stream.send_error(self.task_planner_failure_message)
            return None

        await self.sse_stream.send_chars("# My Plan for Your Request")
        await self.sse_stream.send_mermaid(diagram)
        return diagram
