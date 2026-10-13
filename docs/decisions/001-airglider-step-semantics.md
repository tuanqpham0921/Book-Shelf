# 001: airglider step semantics

**Status:** accepted

## Context

airglider grew out of the app's old `common/operation.py` and `common/workflow.py`. The first version had:

- Two envelope classes: `OperationResult` for a leaf and `WorkFlowOperationResult`, which added `steps`.
- Manual attaching: a workflow ran a child through `run_async_step(..., raise_on_failure=...)`, which attached the envelope and optionally raised.
- Rules about who could call whom (a `@task` couldn't run a workflow).
- `ok` set by whoever felt like it, so "not ok" could mean a crash, an empty result, or a judgment call, and a `@task` could return a hand-built `OperationResult`.

That made the same parent/child relationship get rebuilt in several places (an `isinstance` ladder in `flatten`, `getattr(x, "steps", [])` at every reader). It also left open questions: should `run_async_step` return the envelope or the payload, what happens with an untraced child, and who decides `ok`.

## Decision

1. **Nesting is automatic, through one ContextVar.** The caller publishes its envelope (`parent_scope`), and a child attaches itself on the way out. Any unit can call any other, at any depth. Deep `@task → @task → @task` chains are allowed. They can look redundant, but they show exactly how arguments change between steps, and the developer can flatten or restructure them. The trace is shaped like the code, the way a nested dict is.
2. **One envelope class.** An empty `steps` costs nothing, and once any unit can run another, "leaf or not" can't be known at decoration time.
3. **Two verbs replace `run_async_step`.** `await step` returns the envelope, and `(await step).unwrap()` returns the payload or raises `StepFailure`. Splitting the await from the failure policy is what lets a caller inspect or retry an envelope and then insist.
4. **`ok` means "ran to completion".** The producer judges completeness and raises when it can't complete; the consumer judges sufficiency by reading the payload. An empty result is `ok=True`. Examples: a planner that produced zero goals is ok; a query that found no books is ok; a node with no anchor books to work from raises.
5. **A `@task` returns its payload.** Returning an `OperationResult` raises `TypeError`; `add_details` writes to the task's own envelope instead.
6. **`StepFailure` is logged as a warning without a traceback.** The step that actually failed already logged the real traceback. Re-printing it at every level above turned one cause into four tracebacks.
7. **An untraced function is just Python.** It isn't in the tree. If it raises, the nearest traced caller records the error.
8. **Both `Workflow` and `@task` stay.** A `@task` is function-shaped, and a `Workflow` is class-shaped for grouping steps and state. Neither is required to use the other.
9. **Mermaid rendering moved out** to `app/domains/planjane/dial/`, since PlanJane is the only thing that draws a diagram and is headed for being its own service.

## Consequences

- The trace can be verbose for deep chains of tasks; pruning it is the developer's job.
- Errors are untyped: a business failure and a crash are both a `runtime_error`, so a caller cannot branch on which it was.
- `Workflow.__call__` does not set `ok=True` itself. A `run()` body must, so rule 4 is a convention that the host's base class enforces (BookShelf's `AppWorkflow.finalize_result`).
- Fire-and-forget tasks that outlive their parent attach to an envelope that has already been reported.
- Retry policy is left to the caller for now.
