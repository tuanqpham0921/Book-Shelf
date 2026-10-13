# Eval strategy

BookShelf's eval strategy is to grade the LLM calls that decide what a turn does, one kind of check per question, and to grow coverage by adding cases rather than changing harnesses. How to run each eval, and the suites they read: [backend/evals/](../../backend/evals/README.md).

## Why the system is testable

The steps of a turn talk to each other in natural language: the planner writes each goal as a plain instruction, and each node parses its own arguments from it, with only its own context. So:

- **A node is tested alone,** by handing it an instruction and its inputs.
- **Correctness concentrates in the planner.** If PlanJane emits the right nodes, in the right order, with self-contained instructions, the rest follows. Most of the eval effort goes there.
- **The planner's model is chosen by eval.** It is the one call that sees the whole catalog, so it gets the strongest model that tests well; the identical catalog keeps its cache hit rate high and its short output keeps writes low.

## Three kinds of eval

| Kind | Grades | Why this shape |
|---|---|---|
| **The golden test** (`make suite-goals`) | the planner, through the whole app: its accepted node types against each case's `expected_nodes` | It grades the plan, not execution, so it keeps working as executors change. It reports no numbers that move run to run, so its diffs stay readable. |
| **One call on its own** (`make eval-routing`, `make eval-validation`) | triage's router and the message check, each sent straight to OpenAI by the step's own request builder | No backend, no database, cents per run. Editing the prompt and rerunning is the whole loop. |
| **The catalog** (`make tools-catalog`) | the live registry: what the planner is told, and what that costs per request | It needs no recorded run, so it belongs in the edit loop for any node. |

Spend is a separate report (`make suite-stats`) on purpose, so correctness and cost never share a diff.

**Read a red as "behaviour changed since the baseline".** `expected_nodes` records what the planner accepted on a reviewed run, not a wish list. A red is a regression, or an improvement to re-baseline on purpose.

**The loop:** finalize nodes → build cases around them → set thresholds → grow nodes and coverage together.

## What no eval covers yet

- **The reply.** It runs after every plan, so a plan never lacks it and the goals diff can't see it ([decision 006](../decisions/006-one-reply-stage.md)). Judging it needs an output-grading eval over the recorded runs. Until then, read `/review`.
- **Instruction quality.** The diff checks which node was picked, not whether its instruction was self-contained ([decision 002](../decisions/002-capability-nodes.md)).
- **A dropped intersect.** Pooling and a missing intersect look alike to a node-type diff ([decision 003](../decisions/003-one-dimension-nodes.md)).
- **Answer-level correctness.** "Recommend authors like X" plans the same node types as an easier case; only argument- or answer-level checks tell them apart.
- **Project-info answers.** The `supported` check was tuned on six live questions, run three times each. There is no suite.
- **Each node's own argument parse.** It would follow the single-call pattern, one folder per node.

## Where it is headed

1. **Make `make suite-goals` the release gate,** with thresholds the base and adversarial suites must clear. The extended suite stays out of the gate.
2. **Re-baseline against the current node set.** Cases that assert a plan the taxonomy has since refused (category- or author-anchored "recommend") need re-deciding, not re-running.
3. **One layout for every eval:** a suite, a runner that calls the node directly, and a report ([backlog](../backlog.md)).
4. **More cases:** clarification-expected (references to an earlier turn, over-budget asks, contradictory constraints) in the router suite as much as the planner's; bad words; a fictional series plus "everything by its author".
5. **Case notes in the reports,** so a red is faster to read.
