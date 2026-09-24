# backend/app

The FastAPI application layer: HTTP surface, orchestration, and the domain node system.
Architecture overview lives in the root [CLAUDE.md](../../CLAUDE.md); V1 plans in
[/docs](../../docs/README.md).

## Layout

| Path | What it is |
|---|---|
| `main.py` | FastAPI app factory, CORS, router registration |
| `api/routes/` | One file per router (health, session, chat_message, chat_run, feedback) — `feedback.py` holds two, because only the chat's one is served in production |
| `api/schemas/` | External request/response models (`ChatIn`, `FeedbackIn`, `ReviewIn`, …) |
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
| PUT | `/session/{session_id}/message/{chat_id}/feedback` | The chat's thumbs up/down and comments (`FeedbackIn`: `ReviewIn` without the ids, comments capped by `AppConfig.FEEDBACK_MAX_COMMENTS`/`FEEDBACK_COMMENT_LENGTH`), upserted whole as that session's `feedback` row. 404 unless the run is recorded and this session produced it (`ChatRunStore.belongs_to`) |
| GET | `/chat_runs` | Review queue, least-reviewed first (`limit`/`offset`/`session_id`). **Not served in production** |
| PUT | `/feedback/review` | Upsert one review per (chat_id, session_id) — see `ReviewIn`. **Not served in production** |
| GET | `/feedback?chat_id=` | List reviews for one run. **Not served in production** |

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
   (`orchestration/triage/`), which decides whether to plan at all — replay a
   cached plan, or split the message with a gpt-5-mini query decomposition
   into portions labelled in_domain, small talk, out of scope, security or
   gibberish. The planner is asked the in_domain portions only; a message with
   none gets one fixed reply and no plan.
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
5. `Orchestrator._finalize` then records the turn — **one sink per environment**
   (`orchestration/run_recorder.py`, since 2026-09-23). Production inserts one
   `chat_runs` row (planner/tasks/writer JSONB), which is what the review page and
   the eval reports read and the only durable copy a deployed turn gets; Cloud
   Run's filesystem is in-memory, so files are never the production sink.
   Development writes JSON files under `logs/<chat_id>/` instead — no row, so a
   local turn finishes whether or not Postgres is up. Test writes nothing. Either
   way it never raises. Requests are stateless: nothing reads prior turns back
   (single-turn by design for V1).
