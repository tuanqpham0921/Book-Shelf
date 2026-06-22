from typing import List, Union
from pydantic import BaseModel, Field, field_validator
from app.domains.registry import REQUEST_CLASSES
import logging

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
