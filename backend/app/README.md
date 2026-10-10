intro

how to read the folder structure
registry - specs

folder structure

api endpoints

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


