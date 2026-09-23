# backend/app

The FastAPI application layer: HTTP surface, orchestration, and the domain node system.
Architecture overview lives in the root [CLAUDE.md](../../CLAUDE.md); V1 plans in
[/docs](../../docs/README.md).

## Layout

| Path | What it is |
|---|---|
| `main.py` | FastAPI app factory, CORS, router registration |
| `api/routes/` | One file per router (health, session, chat_message, chat_run, feedback) |
| `api/schemas/` | External request/response models (`ChatIn`, `ReviewIn`, …) |
| `orchestration/` | `Orchestrator` (transport per message), `TriageWorkflow`, `TaskRunnerWorkflow`, run recorder |
| `domains/` | Node type system + PlanJane, the planner — see [domains/README.md](domains/README.md) |
| `common/` | `RequestContext`, `SSEStream`, message types, prompt loading |
| `registry.py` | `Registry` — every node lookup (schema, executor, catalog, planner enum) derived from `SPECS` |

## API surface

| Method | Path | Notes |
|---|---|---|
| GET | `/health`, `/ping` | Liveness |
| GET | `/ready` | Readiness (orchestrator + DB); 503 when not ready |
| POST | `/session/new` | Mints an env-prefixed session id. Writes nothing — the `sessions` row is created by the first message, not here |
| POST | `/session/{session_id}/message` | The chat endpoint — streams SSE events. 400 on a blank or >2000-char message. Reads the session's token budget (which is also what creates its row); a session with nothing left is refused by the orchestrator as an `error` event, not a status code |
| GET | `/chat_runs` | Review queue, least-reviewed first (`limit`/`offset`/`session_id`) |
| PUT | `/feedback/review` | Upsert one review per (chat_id, session_id) — see `ReviewIn` |
| GET | `/feedback?chat_id=` | List reviews for one run |

There is no auth yet — a known pre-deploy blocker (docs/backlog.md, Security P1).

## Request flow (current state)

1. `POST /session/{session_id}/message` validates the message and builds a
   `RequestContext`. It touches no database: the whole token budget is the
   turn's own work, so `Orchestrator.run` opens the session itself with
   `start_session_turn` — one round trip, a `@task` and the turn's first step,
   which also creates the `sessions` row if this is the session's first message.
   A session with nothing left is told so over the stream and the turn ends
   there, before triage, which is the first thing that costs money. **Enforced
   in every environment since 2026-09-23** — the old production-only gate is
   gone, so a `make dev` session or an eval suite now stops when its 50,000
   tokens do. Otherwise the turn goes to `TriageWorkflow`
   (`orchestration/triage.py`), which decides whether to plan at all — replay a
   cached plan, or hand the turn to the planner.
2. `PlanJaneExecutor` (`domains/planjane/`) parses the message into goals against the
   live tool catalog and streams the plan's Mermaid diagram over SSE.
3. `TaskRunnerWorkflow` (`orchestration/task_runner.py`) runs the accepted goals in dependency
   order against the **real** executors (`REGISTRY.spec(...).executor` in
   `registry.py`), for the node types registered on this branch. It
   brackets each node with `task.start` / `task.end` SSE events — closed in a `finally`,
   so a node that raises still closes its UI section — and stamps the node's `num_books`
   onto the section header on close. Retrieval nodes report a count plus a few preview
   cards; only the terminal node fetches the full rows.
4. `Orchestrator._finalize` charges the turn to its session
   (`orchestration/token_budget.py`), using the root envelope's token total — so the
   planner and the reply are billed alongside the tasks. It runs first of the three
   cleanup steps, on its own database session, and never raises. A turn that spent
   nothing — a refusal — writes nothing.
5. Every turn is recorded to the `chat_runs` table (planner/tasks JSONB) —
   that's what the review page and eval reports read. Requests are stateless: nothing
   reads prior turns back (single-turn by design for V1).
