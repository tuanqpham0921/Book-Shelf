from app.domains.node_types import NodeTypeEnum
from typing import Annotated
from pydantic import Field
from pydantic import BaseModel
from pydantic import field_validator
from typing import Optional

SystemGoalDescription = Annotated[str, Field(max_length=100)]
from app.domains.base_request import (GOAL_PLACEHOLDER, 
                                      MIN_STRING_LENGTH, 
                                      MAX_STRING_LENGTH, 
                                      MIN_CONFIDENCE, 
                                      MAX_CONFIDENCE)

MAX_SYSTEM_GOALS = 10
from pydantic import PrivateAttr

class SystemGoal(BaseModel):
    description: str = Field(
        ...,
        min_length=MIN_STRING_LENGTH,
        max_length=MAX_STRING_LENGTH,
        description="Description of the system goal",
    )
    confidence: float = Field(
        ...,
        ge=MIN_CONFIDENCE,
        le=MAX_CONFIDENCE,
        description="Confidence between 0 and 1 that the system can handle this goal",
    )

    target_node_types: NodeTypeEnum = Field(
        ...,
        description="Available request schema to complete this goal",
    )
    
    _refusal_reason: str | None = PrivateAttr(default=None)
    _id: str = PrivateAttr(default=GOAL_PLACEHOLDER)
    
    @property
    def id(self) -> str:
        return self._id
    
    @property
    def refusal_reason(self) -> str | None:
        return self._refusal_reason

    @field_validator("confidence", mode="before")
    @classmethod
    def check_confidence(cls, value):
        if not isinstance(value, (float, int)):
            return MIN_CONFIDENCE
        if not (MIN_CONFIDENCE <= value <= MAX_CONFIDENCE):
            return MIN_CONFIDENCE
        return float(value)

class InitialParseRequest(BaseModel):
    """
    Initial parse for the Book Recommender: extract system_goals with confidence,
    and separate small_talk and out_of_scope from in-domain requests.
    """

    small_talk: Optional[str] = Field(
        default=None,
        max_length=MAX_STRING_LENGTH,
        description="Small talk in the request",
    )
    out_of_scope: Optional[str] = Field(
        default=None,
        max_length=MAX_STRING_LENGTH,
        description="Out-of-domain content",
    )
    system_goals: list[SystemGoal] = Field(
        default_factory=list,
        max_length=MAX_SYSTEM_GOALS,
        description="System goals for the query",
    )
    reasoning: str = Field(
        ...,
        min_length=MIN_STRING_LENGTH,
        max_length=MAX_STRING_LENGTH,
        description="Reasoning for classification",
    )

    @field_validator("small_talk", mode="before")
    @classmethod
    def check_small_talk(cls, value):
        if not isinstance(value, str):
            return str(value)
        if len(value) > MAX_STRING_LENGTH:
            return value[: MAX_STRING_LENGTH - 4] + "..."
        return value

    @field_validator("out_of_scope", mode="before")
    @classmethod
    def check_out_of_scope(cls, value):
        if not isinstance(value, str):
            return str(value)
        if len(value) > MAX_STRING_LENGTH:
            return value[: MAX_STRING_LENGTH - 4] + "..."
        return value

    @field_validator("reasoning", mode="before")
    @classmethod
    def check_reasoning(cls, value):
        if not isinstance(value, str):
            return f"is not a string, padded to the reasoning"
        if len(value) < MIN_STRING_LENGTH:
            value += (
                f"is less than {MIN_STRING_LENGTH} characters, padded to the reasoning"
            )
        if len(value) > MAX_STRING_LENGTH:
            return value[: MAX_STRING_LENGTH - 4] + "..."
        return value

    @field_validator("system_goals", mode="before")
    @classmethod
    def check_system_goals(cls, value):
        if not isinstance(value, list):
            value = [value]
        if len(value) > MAX_SYSTEM_GOALS:
            value = value[:MAX_SYSTEM_GOALS]
        return value
