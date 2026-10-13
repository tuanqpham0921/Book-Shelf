"""Bounded field types for what an LLM fills in: a value out of range is clamped
or trimmed on the way in, rather than failing validation."""

from typing import Annotated

from common.pydantic_validators import bounded_float, bounded_string

MIN_CONFIDENCE = 0.0
MAX_CONFIDENCE = 1.0

MAX_STRING_LENGTH = 100
REASONING_FALLBACK = "(no reasoning provided)"

# NOTE: an instruction gets its own, larger bound because `bounded_string`
# truncates silently: a clipped reasoning is cosmetic, a clipped instruction
# changes what the node does. `Field(max_length=...)` carries it into the tool
# schema, which is how the planner learns the budget.
MAX_INSTRUCTION_LENGTH = 300
INSTRUCTION_FALLBACK = "(no instruction provided)"

ConfidenceFloat = Annotated[float, bounded_float(MIN_CONFIDENCE, MAX_CONFIDENCE)]

ReasoningStr = Annotated[str, bounded_string(
    max_length=MAX_STRING_LENGTH,
    fallback=REASONING_FALLBACK)]

InstructionStr = Annotated[str, bounded_string(
    max_length=MAX_INSTRUCTION_LENGTH,
    fallback=INSTRUCTION_FALLBACK)]
