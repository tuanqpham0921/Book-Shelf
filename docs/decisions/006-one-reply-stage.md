# 006: one reply stage per turn

**Status:** accepted · 2026-09-08, when `Generate_Recommendations` was deregistered

## Context

The reply used to be a node, `Generate_Recommendations`, that the planner had to remember to plan. A plain lookup got cards and no prose, and a writer at the end of one chain saw only that chain. "Do you have It, and show me books like Pride and Prejudice?" is two separate branches, and a writer that saw only one would invent the other half. A sink per branch was tried on branch `generation_node_sink` and collapsed to one per turn.

## Decision

The reply is written by an unregistered stage, `GenerationExecutor`, that the orchestrator runs **exactly once per turn, after every goal**. The planner never picks it.

- **Its input is every goal's result,** plus triage's project facts in front and the planner's out-of-scope portions behind. A project question alone skips the planner and still gets a reply.
- **Its brief is the user's own message.** Nothing the planner wrote steers the prose.
- **A failed or skipped goal leaves a `FailedGoalOutput`,** whose reason names the upstream cause ("it needed 'Find Dune by title', which found nothing"). That lets the reply explain a two-hop failure without knowing the plan's shape.
- **It writes from a report capped per goal,** so the last section, where failures render, always arrives.
- **It returns text and source blocks,** and the source names which books the text talks about, so only books the text points at become cards.

## Consequences

- Every planned turn gets prose, and the planner has no reply goal to get wrong.
- The planner can't tell the writer *what* to write. Book QA and compare, if they arrive, become branches of one prompt rather than slices.
- The golden test can no longer check generation: a stage that always runs is never missing from a plan. Reply quality is checked by reading `/review` until an output-grading eval exists.
