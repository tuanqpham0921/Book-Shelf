# Human-in-the-loop: pause, persist, resume (design record)

**Updated:** 2026-10-08 · **Status:** proposed. Pause point not chosen; nothing built.

The owner rates this the highest-value feature left, and it is also the one most likely
to force architecture changes — which is why the pause point is chosen on paper first.

## What it means here

Interrupt a run, show the user what the system is about to do, and continue from that
point after they answer, rather than running to completion and apologizing.

It needs four pieces, none of which exist:

1. **A pause event** over SSE, with the question and the choices.
2. **Trace persistence** — the run's state saved at the pause, not just logged.
3. **A resume endpoint** — new API surface.
4. **Rehydration** — load the saved state back into live workflow objects and continue
   with the user's answer.

Piece 4 is where the difficulty is.

## Candidate pause points

### A. After the planner — "here's the plan, continue?"

The easiest and most testable. The plan already streams as a Mermaid diagram, so the UI
half is nearly free, and the state to persist is one `PlanJaneOutput`. A gate placed
*before* `TaskRunnerWorkflow` starts touches no concurrency or checkpoint semantics.

### B. On cost — "this will be expensive, continue?"

Warn before running a large plan. Attractive because it generalizes: any step that can
estimate its own cost can gate on it.

### C. After retrieval counts — "4,000 horror books, narrow it down?"

The most useful to a real user, and buildable now: retrieval nodes count and hand on a
`DeferredBookQuery` without fetching rows, so the number exists at every step for free
([execution-pipeline-v1.md](execution-pipeline-v1.md)). The counts already stream as
`ui_loading` lines, so the UI half is nearly free too.

**An empty result needs no question.** If an intersection is empty, the answer is
already known — nothing matches all the criteria — and there is nothing to relax that
would change it. A gate belongs where a count is *large*, not where it is zero.

## Blockers

1. **Child progress is lost on interrupt.** A child's record is attached to its parent
   only when the child finishes (`parent_scope` attaches in `finally`), so an interrupted
   run has no record of partial child work. Better checkpointing needs incremental
   attachment and a rethink of append/overwrite semantics (backlog, Workflow framework).
   A pause *between* workflows (A or B) avoids this; one inside a running task does not.
2. **There is no server-side stop.** Pause/resume and stop want the same plumbing.

## Guardrail: nothing stays alive waiting

> The turn **ends normally**. The next user message resumes the work by reading the saved
> `chat_runs` trace. No workflow, task, or connection stays alive holding state while the
> system waits for a human.

This keeps the V1.1 conversation work additive rather than a re-architecture. A "pause"
built as a suspended coroutine, a held SSE connection, or an in-memory registry would pass
a demo and break the design. Concretely, a pause must:

- finalize and record the run like any completed turn;
- carry enough state in that record to rebuild the plan without the original process;
- treat the user's answer as an ordinary next message that happens to resume something.

## The open problem: a gate mid-plan cannot go back

```
filter1 ─┐
         ├─→ intersect
filter2 ─┘
```

Pausing at the intersect lets the user narrow or relax *that* step, but the upstream
retrievals have already run with fixed arguments. Re-opening one means re-planning part
of the graph. Two candidate answers, neither chosen:

- **Gate only before the reply**, where every count is known and the whole plan can be
  re-run as a unit.
- **Stop rather than ask** when an upstream branch is empty, and let the reply explain it
  from the failure artifacts — which already happens today.

## Scope limits

- **Choices, not free text.** A text box invites "actually compare them instead", which
  is a re-plan, not a resume. Narrow / relax / proceed / stop only.
- **No loop.** A pause is one turn ending and the next resuming from the saved record.
- **At retrieval, a hint, not a gate.** An uncertain title match wants "did you mean this
  one?", and a "no" drops those books from the next step rather than blocking the plan.

## Recommendation

Build **A** first, as a confirm gate before `TaskRunnerWorkflow` starts. It proves the
whole loop (event → persist → endpoint → rehydrate → continue) against the simplest state
in the system, and makes B and C incremental rather than foundational. The plan can
already be rebuilt from JSON: `Registry.request_union()` derives the union of request
schemas from the registered specs.
