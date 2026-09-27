"""USD rates for the models the host app calls — **USD per 1M tokens**.

The one part of airglider that is policy rather than mechanism. It lives here
so `TokenUsage` can stamp `cost_usd` with no wiring; if a host ever needs other
providers, the seam to cut is `cost_of` — inject it rather than import it.

**These go stale.** OpenAI reprices without notice and drops superseded models
off the index page. Re-verify before trusting a cost figure that matters, and
bump PRICES_CHECKED_ON when you do.

Billing shape (mirrors `ModelUsage`): `cached` is a subset of `prompt`, so the
full-rate portion is prompt - cached; `reasoning_tokens` is a subset of
`completion`, already billed at the output rate — never add it on top.
"""

from typing import NamedTuple

PRICES_CHECKED_ON = "2026-07-24"

PER_MILLION = 1_000_000

#: Bucket for token usage whose originating model was never recorded. Keeps the
#: invariant that per-model counts sum to the flat total, instead of silently
#: dropping the tokens on the floor.
UNKNOWN_MODEL = "unknown"


class ModelPrice(NamedTuple):
    """USD per 1M tokens."""

    input: float
    cached_input: float
    output: float


MODEL_PRICES: dict[str, ModelPrice] = {
    # the planner's goal-parse step pins this one (planjane/executor.py) — it
    # sees the whole tool catalog every request, so it dominates a run's cost.
    # Added 2026-09-24.
    "gpt-6-sol": ModelPrice(input=2.00, cached_input=0.20, output=10.00),
    # the message check's model (orchestration/validation/validate.py).
    # Added 2026-09-26.
    "gpt-6-luna": ModelPrice(input=0.10, cached_input=0.01, output=0.50),
    # former planner model; priced here for older recorded runs
    "gpt-5.6-luna": ModelPrice(input=1.00, cached_input=0.10, output=6.00),
    # an earlier parse-step model; priced here for older recorded runs
    "gpt-4.1": ModelPrice(input=2.00, cached_input=0.50, output=8.00),
    "gpt-4.1-mini": ModelPrice(input=0.40, cached_input=0.10, output=1.60),
    "gpt-4.1-nano": ModelPrice(input=0.10, cached_input=0.025, output=0.40),
    "gpt-5-mini": ModelPrice(input=0.25, cached_input=0.025, output=2.00),
    "gpt-5-nano": ModelPrice(input=0.05, cached_input=0.005, output=0.40),
    # embeddings bill input only — the zero rates are structural, not unknown.
    # Added 2026-08-17 (the recommend node's similarity search).
    "text-embedding-3-small": ModelPrice(input=0.02, cached_input=0.0, output=0.0),
    "text-embedding-3-large": ModelPrice(input=0.13, cached_input=0.0, output=0.0),
}


def price_for(model: str) -> ModelPrice | None:
    """Rate for `model`, or None if it isn't priced here.

    Falls back to the longest matching prefix so pinned snapshot names
    (`gpt-4.1-mini-2025-04-14`) resolve to their base model's rate.
    """
    if not model:
        return None
    if model in MODEL_PRICES:
        return MODEL_PRICES[model]

    prefixes = [name for name in MODEL_PRICES if model.startswith(name)]
    return MODEL_PRICES[max(prefixes, key=len)] if prefixes else None


def cost_of(model: str, prompt: int, cached: int, completion: int) -> float | None:
    """USD for one model's token counts, or None if the model isn't priced.

    None is deliberately distinct from 0.0: an unpriced model means *unknown
    spend*, not *free*.
    """
    price = price_for(model)
    if price is None:
        return None

    full_rate_prompt = max(prompt - cached, 0)
    return (
        full_rate_prompt * price.input
        + cached * price.cached_input
        + completion * price.output
    ) / PER_MILLION
