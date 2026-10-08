# Evaluation strategy

**Updated:** 2026-10-08 · Operational how-to is in
[../backend/evals/README.md](../backend/evals/README.md). This doc covers what each eval
is for, what it cannot see, and what is still to build.

## Three kinds of eval

### 1. The planner, through the whole app — the golden test

The suite JSONs in `backend/evals/planjane/suites/` are versioned inputs with a per-case
`expected_nodes`. `run_suites.py` fires each query at a running backend and records one
`test_runs` row per query (chat_id FK → `chat_runs`, plus the suite name and case id).

- **`make suite-goals`** (`report_system_goals.py`) joins `test_runs ⋈ chat_runs` and
  multiset-diffs the planner's accepted goal types against `expected_nodes`:
  matched / missing / extra per case. Correctness only, so the diff never churns on
  numbers that move every run.
- **`make suite-stats`** (`report.py`) reports the spend: ok/failed, runtime errors,
  duration, tokens, cache hit rate, dollars, per-model split.
- `make suite-reports` runs both.

Why this is the right foundation:

- **It grades the plan, not execution,** so it keeps working unchanged as executors
  change.
- **It grows by adding JSON cases,** not by changing the harness. New node → new cases.

The intended loop: finalize nodes → build cases around them → set thresholds → grow
nodes and coverage together.

**Read a red as "behaviour changed since the baseline"** — a regression, or an
improvement that should be re-baselined on purpose. Since the 2026-07-24 relabel,
`expected_nodes` records what the planner actually accepted on a reviewed run, not a
wish list.

### 2. One LLM call on its own

A step that is one call over one schema is graded without the backend or database: the
step's own request builder goes straight to OpenAI.

| Eval | What it grades | Run |
|---|---|---|
| `evals/triage/` | Triage's router — passes when the tool picked (or `reply`) is one of the case's expected routes | `make eval-routing` |
| `evals/validation/` | The message check | `make eval-validation` |

A node's own `*Args` parse would follow the same pattern under `evals/nodes/<node>/`.
None exists yet.

### 3. The catalog itself

`make tools-catalog` reads the live registry: tool count per tier, per-tool token cost,
the per-request price of shipping the catalog, and an audit for nodes with no executor
or docstrings missing a canonical section. Run it after adding or editing a node.

## What no eval covers yet

- **The reply.** It is written by a stage that runs after every plan, so it is never
  missing from a plan and the goals diff cannot check it. Judging it needs an
  output-grading eval over `chat_runs.tasks` (the stage's record, and its text in it),
  which is not built. Until then, reply quality is checked by reading `/review`.
- **Instruction quality.** The diff checks which node was picked, not whether its
  instruction was self-contained.
- **A dropped intersect.** Pooling and intersecting look alike to a node-type diff when
  the intersect is missing (see [design/execution-pipeline-v1.md](design/execution-pipeline-v1.md)).
- **Answer-level correctness.** Cases like "recommend authors like X" expect a books plan
  whose node types are identical to an easier case; only argument- or answer-level
  checking would tell them apart.
- **Project-info answers.** The `supported` check on `Retrieve_Project_Info` was tuned on
  six live questions, run three times each. There is no suite for it.

## Suite inventory

| Suite | Cases | Purpose |
|---|---|---|
| `query_suite.json` (base) | 80 | Core node set, easy → hard, single lookups to multi-node chains |
| `query_suite_adversarial.json` | 54 | Rejection: prompt injection, impossible facts, degenerate input (17 cases expect no nodes) |
| `query_suite_stress.json` | 9 | Past `MAX_SYSTEM_GOALS`, confusing multi-hop chains |
| `query_suite_extended.json` | 48 | Catalog scaling (~26 node types). **Dormant:** reviving it means giving the playground schemas real `NodeSpec`s |

`make query-suite-all` fires all four concurrently, which doubles as the concurrency
test. `make query-suite-smoke` runs the first three with no sleep, for debugging.

**Budget note:** the session token budget is enforced in every environment, and
`run_suites.py` reuses one session per run, so a long suite needs
`--new-session-per-query` or a larger `SESSION_TOKEN_BUDGET`.

**Where results live:** planner campaigns under `backend/evals/app_docs/results/`
(one folder per campaign, e.g. `v1_baseline/`); triage and validation runs under their
own `results/` folders.

## Still to do

- **Set thresholds** and make `make suite-goals` the release gate: base + adversarial
  must clear theirs for V1 to ship.
- **Re-baseline against the current node set.** The last full baseline predates triage
  and several taxonomy changes; cases that assert a plan the taxonomy has since refused
  (for example category- or author-anchored "recommend" cases) need re-deciding, not
  just re-running.
- **Clarification-expected cases:** prior-turn references ("that one from earlier"),
  over-budget requests, contradictory constraints. Triage now answers these, so they
  belong in `evals/triage/suites/route_query.json` as much as in the planner suites.
- **The owner's pending cases:** bad words, and a fictional series plus "everything by
  its author" (nonexistent-entity behaviour).
- **Keep the extended suite out of the release gate.**
- **Surface case notes in reports** to make reds faster to read.
