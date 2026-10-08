# Execution pipeline (design record)

**Updated:** 2026-10-08 · **Status:** built. Counts-first retrieval, CTE composition, the
combine tier (intersect only) and the one-per-turn reply stage all run today.

How a plan executes once the planner has written it. Which nodes exist is in
[node-taxonomy-v1.md](node-taxonomy-v1.md); the pause points this shape creates are in
[human-in-the-loop.md](human-in-the-loop.md).

## The shape

| Tier | Job | Hands on |
|---|---|---|
| **Retrieval** | Resolve one dimension; **count, don't fetch** | A count, a composable query, and a 4-book preview |
| **Combine** | Compose upstream queries into one CTE (AND today) | A narrowed query, still not materialized |
| **Analyze** | Interpret what it was given (similarity search today) | A scored query |
| **Reply stage** *(not a node)* | Write the answer from every goal's result | Text blocks and the cards they point at |

The load-bearing idea: **retrieval does not materialize rows.** A retrieval node runs a
`COUNT`, keeps a small preview for its cards, and hands on a `DeferredBookQuery`. A later
node composes against that query in SQL rather than filtering a list someone fetched.

Why:

1. **Counts are known at every step** before any large result is built — the natural
   pause point for "that's 4,000 horror books, narrow it down?"
   ([human-in-the-loop.md](human-in-the-loop.md)).
2. **Cross-column asks have a home** without putting a filter object back on a
   planner-facing schema: "sci-fi over 300 pages" is two retrievals and an intersect.
3. **Intersecting capped lists would be wrong.** Two 4-book previews almost never
   overlap; two queries intersected in SQL give the real answer.

**Accepted cost:** more round trips — a count and a preview per retrieval. Fine for a
demo whose LLM calls take seconds.

## `DeferredBookQuery`

`db/stores/deferred_query.py`. A SELECT of `isbn13` plus an optional `score`, built by
module-level pure functions in `db/stores/book_store.py` (`title_query`, `author_query`,
`numeric_traits_query`, `lexical_query`, `embedding_search_stmt`). `BookStore` is only the
execute half: `count`, `score_stats`, `materialize`. Building, recording and composing a
query never checks out a connection.

**Invariant: no LIMIT and no ORDER BY.** That is what makes a query composable;
`materialize_stmt` adds the ordering (by `score` when present, else rating) and the cap.

**The one exception is the vector search.** It does not select a subset — it orders the
whole table by cosine distance and truncates — so the cap (`CANDIDATE_POOL_SIZE = 250`,
about 5% of the catalog) *is* the pool. Consequences:

- `count()` on it only reports the cap. `score_stats()` (count plus min/max/avg score) is
  its counting call.
- Nothing on the class marks the exception, and `compose()` does not refuse it. A guard
  was tried and removed as machinery for a caller that did not exist.
- The LIMIT applies before any set operation, so an intersect's count means "of the 250
  nearest, N also match". That is accepted and documented, not shown in the UI.

## Composition

`DeferredBookQuery.compose(queries, op)` folds several queries into one CTE.

- **`op="and"` carries one `score` through** when exactly one input has one. An
  intersection is a subset of every input, so that column is defined on every output row.
  This is what keeps "books like Dune under 300 pages" in cosine order. Two scored inputs
  (say a trigram score and a `ts_rank`) are incommensurable, so both are dropped.
- **`op="or"` drops every score.** A union contains rows the scored input never matched.
  A pooled query therefore ranks by rating, and a similarity pool pooled with anything
  loses its ranking entirely and skews the branch proportions.

**Before registering `Combine_Union`,** either tune `MIN_SIMILARITY` so the vector search
needs no LIMIT (which dissolves the problem), or restore a compose guard for scored
inputs under `"or"`.
`tests/unit/db/stores/test_deferred_query.py` pins the current behaviour.

## The combine tier

`Combine_Intersect` is registered; `Combine_Union` is not.

- **One operation per node.** The combine node carries no filters of its own. A bound is
  always a retrieval (`Retrieve_by_Numeric_Traits`), and narrowing by it is that
  retrieval intersected with the subject. One way to express a bound, not two.
- **Pooling is implicit.** Several ids in one `depends_on` already mean OR, so
  `Combine_Union` is only for when the pooled set is itself a step something consumes.
  A plan cannot distinguish "meant to pool" from "forgot to intersect", and the
  node-type diff in `report_system_goals.py` cannot catch a dropped intersect. Known
  blind spot.
- **No combine node may depend on `Retrieve_Random`** (once it exists). Intersecting a
  one-book pick discards it almost always, and the empty result looks like "nothing
  matched". Bounds on a surprise go in its own `filters`. Convention only.
- **A failed dependency widens the answer.** With three retrievals and one failed, the
  intersect still has two inputs and runs, answering a looser question. The runner marks
  the failed goal and the node records the counts it intersected ("12 ∩ 340") in its
  details, so the trace shows it, but nothing refuses it.

## Running the plan

`TaskRunnerWorkflow` (`app/orchestration/task_runner.py`) takes
`TaskRunnerInput(plan: PlanJaneOutput)`, runs goals in dependency order, and builds each
node's input with `build_input(spec.input, goal.instruction, dependency_outputs)`. Fields
are filled by type; a required field that matches nothing skips that one goal, naming
the field.

**Failure artifacts.** A goal that fails, is skipped, or was never reachable leaves a
`FailedGoalOutput` in the results instead of nothing. Its reason is written as prose and
names the upstream cause ("it needed 'Find Dune by title', which found nothing"), so the
reply can explain a two-hop failure without knowing the plan's shape. A
`FailedGoalOutput` fills no book-shaped field, so the skip cascade is unaffected.

**`TaskResult`** wraps each goal for the rest of the turn: the node's output plus a
summary of its envelope (duration, total/input/output tokens, error type and message).
`TaskRunnerOutput.task_results` is the turn's source of truth — what the reply is written
from, and what a later turn would read.

## The reply stage

`Orchestrator._write_reply` runs `GenerationExecutor` (`app/orchestration/write_reply/`)
**exactly once per turn**, after the runner. It is not a node and the planner never picks
it.

**Input:** every `TaskResult`, plus triage's `project_info` in front (when triage looked
facts up) and the planner's `out_of_scope` portions behind, as `FailedGoalOutput`s. A
project question alone skips the runner and still gets a reply. The user's own message is
the brief; nothing the planner wrote steers the prose.

**What the writer sees** (`render.py`), capped per goal rather than as a whole, so the
last section — where failures render — always arrives:

- an `<info>` block of at most 400 characters: outcome, error message, parsed arguments,
  cost, and SQL last so the cap cuts it first;
- up to four books from the node's `preview`, at most 600 characters each, labelled with
  a handle (`1.2` = section 1, book 2);
- for a project lookup, a `<project>` block with the answer and its sources.

**What comes back:** `GenerationResult`, a list of `text` and `source` blocks. A `source`
names the handles of the books the text before it talks about, and `books_by_handle`
resolves them against the same list the report was rendered from. The stage sends the
blocks in order, so the answer reads paragraph → its cards → next paragraph, and only
books the text points at become cards.

**Why one stage per turn, not a goal.** The reply sees the whole turn: "Do you have It,
and show me books like Pride and Prejudice?" is two separate branches, and a writer that
only saw one branch would invent the other half. Every planned turn gets prose, and the
planner has no reply goal to get wrong. The cost: the planner cannot tell the writer
*what* to write, sibling replies (book QA, compare) become branches of one prompt rather
than slices, and the golden test can no longer check generation — a stage that always
runs is never missing from a plan (see [eval-strategy.md](../eval-strategy.md)).

A reply stage that fails sends `Orchestrator.reply_failure_message` as an `error` event,
so the stream never ends on task sections with no reply.

## Open questions

- **`MIN_SIMILARITY = 0.35` has never been tuned.** `score_stats` is the instrument: a
  `min` resting on 0.35 means the floor never binds and the cap is choosing the pool. A
  tuned floor that bounds the pool below 250 would let the LIMIT go and restore the
  invariant outright.
- **Analyze-book node.** Question-answering about one book ("is it right for a
  12-year-old?") needs it, and so does `Analyze_Compare`. Not designed yet.
- **`compile_sql` inlines literals,** so a similarity search's recorded SQL carries the
  anchors' ISBNs — and the writer sees that SQL in `<info>`. The prompt says never to
  repeat it.
- **Carrying `max(score)` through a union** would fix pooled ranking; not built.
