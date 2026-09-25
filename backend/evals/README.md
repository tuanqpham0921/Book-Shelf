# backend/evals

Evals, one folder per thing under test. **Why it's built this way and where it's
headed:** [docs/eval-strategy.md](../../docs/eval-strategy.md).

| Path | What it grades |
|---|---|
| `planjane/` | The planner, through the whole running app — versioned query suites with per-case node expectations, the runner, the two DB reports, and the tool catalog |
| `triage/` | Triage's query decomposition alone — one LLM call per case, no backend, no database (see [Triage](#triage--query-decomposition-triage)) |
| `common.py` | Shared plumbing. It sits here rather than in `planjane/` because a script puts its own folder first on `sys.path`, and a `common.py` there would shadow the backend's `common` package |
| `results/`, `logs/` | Campaign outputs and run logs, for every folder above |

A node's own `*Args` parse would get the same treatment as triage, under `nodes/<node>/`.

## PlanJane suites (`planjane/suites/`)

| Suite | Cases | Targets |
|---|---|---|
| `query_suite.json` | 70 | Core node set, easy→hard |
| `query_suite_adversarial.json` | 54 | Rejection behavior (17 cases intentionally expect no nodes) |
| `query_suite_extended.json` | 48 | Catalog scaling — dormant: needs the playground schemas given `NodeSpec`s and passed to `Registry` (see `backend/playground/README.md`) |
| `query_suite_stress.json` | 9 | Buffer/overflow, confusing chains |

Each case: `id`, `query`, `difficulty`, `expected_nodes`, `note` (+ `category`/`domain`
in adversarial/stress).

## PlanJane workflow

Backend must be running (`make dev`). Every path in `makefile` is anchored to the
evals directory, so these run identically from `backend/` (via the root Makefile's
include) or from `evals/` itself (`make -f makefile <target>`). Run logs land in
`evals/logs/query_suites/` either way — override with `LOG_DIR=...`.

```bash
make query-suite            # base suite
make query-suite-adversarial / -extended / -stress
make query-suite-all        # all 4 concurrently (doubles as the concurrency test)
make query-suite-all-seq    # sequential; -all-tmux for one pane per suite
make query-suite-smoke      # first 3 queries, no sleep — the debug loop
```

`LIMIT=n` caps the queries per suite and `SLEEP=n` overrides the 45s the runner waits
between them; both apply to every target above. A full campaign needs that sleep to
stay under the OpenAI TPM limit, a debug run does not — so `make query-suite LIMIT=3
SLEEP=0` finishes in seconds. `query-suite-smoke` is exactly that pairing (override the
count with `SMOKE_LIMIT=n`). Smoke runs record to `chat_runs`/`test_runs` like any
other, so both reports work on them.

The runner (`planjane/run_suites.py`) POSTs each query to `/session/{id}/message`, consumes the
SSE stream, and records its `test_runs` row (chat_id FK → `chat_runs` + suite name +
case id) right away — not batched until the run finishes — so an interrupted run still
has everything it completed recorded. Sessions are minted as `test_<uuid8>` so eval
traffic is filterable. By default it sleeps 45s between queries to stay under the
OpenAI TPM rate limit (`--sleep 0` to disable). Flags: `--suite`, `--difficulty`,
`--ids`, `--new-session-per-query`, `--no-record`, `--sleep`.

Then post-process:

```bash
make suite-goals   # report_system_goals.py — CORRECTNESS. Joins test_runs ⋈ chat_runs
                   # and diffs accepted goal types vs expected_nodes
                   # (matched/missing/extra) → results/system_goals_<timestamp>.md
make suite-stats   # report.py — COST. ok/failed, runtime_error, duration, tokens
                   # incl. cached + cache hit rate, dollars, and a per-model split
make suite-reports # both
```

Both take `ARGS="--all"` for every run (default: latest run per case), `ARGS="--suite
<stem>"` (repeatable) and `ARGS="--output <path>"`. The split is deliberate: the goals
report is the pass/fail gate and mentions no numbers that change run to run, so its
diffs stay readable; the cost report is where tokens, dollars and latency live.

## Tool catalog (`planjane/tools_catalog.py`)

```bash
make tools-catalog                        # print
make tools-catalog CAMPAIGN=v1_baseline   # -> results/v1_baseline/tools_catalog.md
make tools-catalog ARGS="--model gpt-5-nano"
```

The odd one out: it reads the **live registry**, not the database, so it needs no
backend, no prior run and no `chat_runs` rows — it describes the code at the current
commit. Run it after adding or editing a node.

Every registered node is a tool the planner is told about, and its class docstring *is*
the tool description — so the catalog is prompt text billed on **every** request,
whether or not any of those tools get used. The report gives the tool count per tier,
each tool's `Purpose:` line, per-tool token cost with its share of the block, and what
the whole thing costs per request, uncached and cached (the catalog is byte-identical every time, so the cached
column is the steady state — `make suite-stats`'s measured hit rate says how close you
are to it). Two token figures, paid at different points:

- **catalog tokens** — the whole `Registry.format_catalog()` block, rendered into both
  the goal-generator and parse-response prompts, so it is paid twice per request;
- **schema tokens** — one node's JSON function-tool schema, sent by
  `strategy_classification.py` only for the nodes an accepted goal targets.

It also audits: nodes registered with no executor (planned but unrunnable, still paying
catalog tokens) and docstrings missing a canonical section — a missing `Do not use:` or
`Example queries:` is a known misroute source, see
[docs/eval-strategy.md](../../docs/eval-strategy.md).

Dollar figures come from `cost_usd`, stamped onto each run's `token_usage` when it was
recorded (rates in [airglider/src/config.py](../airglider/src/config.py)) — **frozen at record time**,
so re-running a report never backfills or reprices history. Two distinct gaps get called
out rather than hidden:

- a run with no `cost_usd` at all (predates cost tracking) counts as **unpriced** in the
  summary row, never as free;
- a run whose `token_usage.unpriced_models` is non-empty still *has* a cost, just too low
  — the report prints an explicit "costs are understated" warning naming the models. Add
  them to `airglider/src/config.py`; only future runs will be right.

## Triage — query decomposition (`triage/`)

```bash
make eval-decomposition                          # every case, printed
make eval-decomposition ARGS="--ids 1 5 9"       # a few, while iterating
make eval-decomposition CAMPAIGN=v1_triage       # -> results/v1_triage/query_decomposition.md
make eval-decomposition ARGS="--save"            # -> app_docs/results/query_decomposition_<timestamp>/
```

`--save [DIR]` writes `report.md` and `results.json` (every case's full parsed
decomposition — portions and reasoning — plus its grade and token usage) into a
timestamped folder under `DIR`, `app_docs/results/` by default. Progress prints to
stderr as each case finishes.

Grades the gpt-5-mini split that triage runs ahead of the planner, on its own: no
backend, no database, no `test_runs` rows. `eval_query_decomposition.py` sends each
case in `triage/suites/query_decomposition.json` through `build_decomposition_request`
— the builder a real turn uses, so the prompt, model and `QueryDecomposition` tool are
exactly what production sends — straight to `OpenAIClient`, and grades the parsed
portions. The builder reads `decompose_query.txt` from disk on every call, so editing
the prompt and rerunning is the whole loop. It costs real calls: a few cents for the
whole suite.

A case (`id`, `query`, `expected` verdicts in message order, `note`) passes on two
checks:

- **verdicts** — equal to `expected` once adjacent repeats are merged on both sides.
  `[in_domain, in_domain]` and `[in_domain]` give the planner the same words and the
  user the same reply, so a split the app can't act on is not a failure.
- **verbatim** — every portion's text appears in the message exactly as written, the
  prompt's "copy, never correct" rule.

The report lists each case, then every failure with the portions the model returned,
its reasoning and the case's note. Cases lifted from the prompt's own Examples section
say so in their note, since those partly test recall. Earlier turns can't be given yet
— `build_decomposition_request` takes the message alone — so a follow-up case expects
`gibberish` unless it makes sense as a query on its own ("more sci-fi please").

## Repo sizing (`app_docs/`)

Also not about planner quality — two notebooks on making the **repo itself** retrievable
for project/code guidance. `app_docs/token_budget.ipynb` counts the code and docs to size a
do-it-yourself index (tokens, chunks, index MB, dollars, retrieval-vs-whole-corpus cost per
question); local counting only, no API calls and no database. `app_docs/file_search_docs.ipynb`
takes the managed route — uploads `docs/` to an OpenAI vector store and queries it with the
hosted file search tool; that one does spend money and leaves state on the account. See
[app_docs/README.md](app_docs/README.md).

## Campaign convention (`results/`)

Per campaign: a directory with the raw SQL dumps of `chat_runs` + `feedback` (dump
before deleting — `test_runs` cascades away with `chat_runs`), the generated reports,
and a hand-written review (`personal_report.md`, optionally an AI review). See
`results/dev_f5a12966_7_13_initial/` for the shape.

`CAMPAIGN=<name>` files both reports into `results/<name>/` under fixed names, so
`suite-reports` can't have one clobber the other:

```bash
make suite-reports CAMPAIGN=v1_baseline
# -> results/v1_baseline/system_goals.md + results/v1_baseline/report.md
```
