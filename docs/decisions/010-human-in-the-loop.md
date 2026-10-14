# 010: human-in-the-loop: pause, persist, resume

**Status:** proposed. Nothing is built.

## Context

Human-in-the-loop means interrupting a run, showing the user what the system is about to do, and continuing from that point after they answer, instead of running to completion and apologizing. It is the feature most likely to force architecture changes, which is why the pause point is chosen on paper first.

It needs four pieces, none of which exist: a pause event over SSE, the run's state persisted at the pause, a resume endpoint, and rehydration of that state into live workflows. Rehydration is the hard part.

There are three candidate pause points:

- **A. After the planner:** "here's the plan, continue?" The plan already streams as a diagram, and the state is one `PlanJaneOutput`.
- **B. On cost:** "this will be expensive, continue?" It generalizes to any step that can estimate its own cost.
- **C. After retrieval counts:** "4,000 horror books, narrow it down?" This is the most useful to a user, and counts-first retrieval already has the number at every step ([005](005-counts-first-retrieval.md)). An empty result needs no question, so the gate belongs where a count is large, not where it is zero.

Two things block it:

1. **Child progress is lost on interrupt.** A child's record attaches to its parent only when the child finishes. A pause *between* workflows (A or B) avoids this; one inside a running task does not.
2. **There is no server-side stop,** and pause and stop want the same plumbing.

## Decision (proposed)

Build **A** first, as a confirm gate before the task runner starts. It proves the whole loop against the simplest state in the system and makes B and C incremental. The plan can already be rebuilt from JSON (`Registry.request_union()`).

**Guardrail: nothing stays alive waiting.** The turn ends normally, and the next message resumes from the saved `chat_runs` record. No workflow, task or connection holds state while a human decides. A pause must finalize and record the run like any turn, carry enough state to rebuild the plan without the original process, and treat the answer as an ordinary next message.

**Scope:** choices, not free text (narrow, relax, proceed, stop), since a text box invites a re-plan. At retrieval, it is a hint ("did you mean this one?"), not a gate.

## Consequences

- It builds on the V1.1 multi-turn work instead of re-architecting it.
- **A gate mid-plan can't go back.** Pausing at an intersect lets the user change that step, but the retrievals before it already ran with fixed arguments. Two answers, neither chosen yet: gate only before the reply, where the whole plan can re-run as a unit, or stop rather than ask when a branch is empty and let the reply explain it.
