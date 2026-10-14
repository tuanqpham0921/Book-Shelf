# 011: a node can say "wrong node for this"

**Status:** proposed. Nothing is built.

## Context

A node handed work it can't do has two answers: finalize ok (claiming it did the job) or raise (claiming the code broke). The honest third answer, "I ran fine, and this was the wrong node", doesn't exist. That shows up in two ways:

1. **The argument parser can't decline.** With one tool model, the request pins `tool_choice`, so the parse is mandatory. "A book about war" sent to `Retrieve_by_Title` parses to `title="war"`, counts its matches and finalizes ok, which is indistinguishable from a real title search.
2. **An empty result is right for the producer and wrong for the consumer.** `num_books == 0` is a real answer, but composed into the next node it is an OR branch that contributes nothing while making the input look filled. The similarity node already sets empty anchors aside and raises when none are left.

## Decision (proposed)

- **Let the parser choose the tool.** When it declines, its text is the refusal ("this node needs a book title"), and the node finalizes **not ok with no runtime error**, carrying the message to the reply through its `FailedGoalOutput`.
- **Skip a consumer whose dependencies are all empty,** rather than answering in the producer (the reply would say "found nothing" twice) or withholding outputs in each consumer.

This amends executor rule 3 in [the domains README](../../backend/app/domains/README.md#writing-an-executor) ("raise; never set `ok=False` by hand"). Raising puts a business dead-end and a crash in the same `runtime_error`, and a mis-routed goal is a third thing.

## Consequences

- Touches `clients/openai_requests.py` (optional `tool_choice`), `run_llm_tool_calls` (no tool call becomes the refusal), each slice's `finalize_result`, and the task runner.
- Open: whether the refusal rides on a new output field or on `details`, and whether the planner is re-invoked in the same turn. That would be a re-plan loop, the same machinery as clarification across turns.
- **When to build it:** when `make suite-goals` shows mis-routes a declining parser would have caught, or a trace shows a forced parse giving a confident wrong answer.
