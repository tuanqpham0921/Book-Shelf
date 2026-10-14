"""Write_reply is the stage that writes the turn's reply. Not a node: no `SPEC`
and no request schema, since the planner cannot pick it; the orchestrator runs
it once, after the task runner. Import from this package root."""

from .executor import GenerationExecutor
from .external import (
    GenerationResult,
    RecommendationsInput,
    RecommendationsOutput,
    SourceBlock,
    TextBlock,
)

__all__ = [
    "GenerationExecutor",
    "GenerationResult",
    "RecommendationsInput",
    "RecommendationsOutput",
    "SourceBlock",
    "TextBlock",
]
