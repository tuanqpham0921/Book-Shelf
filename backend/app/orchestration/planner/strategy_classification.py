from dataclasses import dataclass

from typing import List, Union

from pydantic import BaseModel, Field, field_validator

from app.common.messages import AssistantMessage, UserMessage, ToolMessage
from app.common.prompt_loader import format_prompt
from app.common.sse_stream import SSEStream
from app.domains.registry import REQUEST_CLASSES
from clients.openai_client import OpenAIClient
from clients import OpenAIParserRequest
from app.common.workflow import UserFacingBaseWorkflow, UserFacingOutput
from config import BookConstraints, BookGuides
from app.orchestration.planner.parse_intent import SystemGoal
import logging
import json
import traceback
from dataclasses import field

logger = logging.getLogger(__name__)


MAX_GOALS = 15
MAX_STRATEGIES = 15

StrategyType = Union[REQUEST_CLASSES]


class StrategyRequest(BaseModel):
    """
    Generate a set of strategy requests to satisfy the user's request.
    Each strategy should represent a discrete unit of work.
    The strategies should be a list of the request classes in the REQUEST_CLASSES tuple.
    """

    strategies: List[StrategyType] = Field(
        default_factory=list,
        max_length=MAX_STRATEGIES,
        description="List of strategies generated from the query",
    )

    @field_validator("strategies", mode="before")
    @classmethod
    def check_strategies(cls, value):
        if not isinstance(value, list):
            value = [value]

        seen_ids: set[str] = set()
        deduped = []
        for item in value:
            item_id = (
                item.get("id") if isinstance(item, dict) else getattr(item, "id", None)
            )
            if item_id is not None:
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)
            deduped.append(item)

        return deduped[:MAX_STRATEGIES]


@dataclass(slots=True)
class StrategyClassificationOutput(UserFacingOutput):
    accepted: list[StrategyType] = field(default_factory=list)
    refused: list[StrategyType] = field(default_factory=list)
    continue_pipeline: bool = field(default=False)

    def to_summary(self) -> dict[str, bool | int | list[str]]:
        return {
            "strategy_ids": [strategy.id for strategy in self.accepted],
        }

    def get_accepted_id_to_node(self):
        """Return dict of node_id -> serialized node data."""
        return {node.id: node for node in self.accepted}


class StrategyClassificationWorkflow(
    UserFacingBaseWorkflow[StrategyClassificationOutput]
):
    success_message = "Strategy classification completed successfully"
    failure_message = "Strategy classification failed"
    ui_loading_message = "Strategizing way to complete goals..."

    _SYSTEM_PROMPT_PATH = "orchestration/planner/prompts/2_strategy_classification.txt"

    tool_models = [StrategyRequest]

    def __init__(
        self, sse_stream: SSEStream, user_message: UserMessage, llm_client: OpenAIClient
    ):
        super().__init__(
            llm_client=llm_client,
            sse_stream=sse_stream,
            output_type=StrategyClassificationOutput,
        )
        self.user_message = user_message

    async def run(self, system_goals: list[SystemGoal]) -> None:
        """Classify the user query into book-related strategies."""
        if not system_goals:
            raise ValueError("System goals are required")

        await self.sse_stream.send_ui_loading(self.ui_loading_message)

        system_prompt = format_prompt(
            prompt_path=self._SYSTEM_PROMPT_PATH,
            book_constraints=str(BookConstraints()),
            book_guides=str(BookGuides()),
        )

        req = OpenAIParserRequest(
            prompt=system_prompt,
            messages=[self._format_system_goals(system_goals)],
            tool_models=self.tool_models,
        )
        assistant_msg = await self.run_llm_call(req)
        tool_call = assistant_msg.tool_calls[0]
        parse_result = tool_call.function.parsed_arguments

        # TODO:
        # Continue here
        # let call be the goal id rejection
        # exapdn the result field to add reasoning for the rejection
        # then you can add reasonings in there easier
        # __call__ handle all the rejection and accepted logic and filling out
        # the result field
        # we might want to do the same for base requests and also the task planner

        
        self.process_classification_result(parse_result)
        self.finalize_result()

    def _format_system_goals(self, system_goals: list[SystemGoal]) -> AssistantMessage:
        payload = [
            {
                "id": goal.id,
                "description": goal.description,
                "confidence": goal.confidence,
            }
            for goal in system_goals
        ]
        return AssistantMessage(content=json.dumps(payload))

    def process_classification_result(self, parse_result: StrategyRequest, accepted_tuning: float = 0.7):
        """Convert to ClassificationResult format"""

        for strategy in parse_result.strategies:
            if (
                strategy.refusal
                or strategy.confidence < accepted_tuning
                or not strategy.target_goal
            ):
                self.output.refused.append(strategy)
            else:
                self.output.accepted.append(strategy)

        self.output.continue_pipeline = bool(len(self.output.accepted) > 0)
        return self.output

    def finalize_result(
        self,
    ) -> None:
        
        super().finalize_result(ok=bool(True))
