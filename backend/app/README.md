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
| `common/` | `RequestContext`, `SSEStream`, the ending tools, field types, prompt loading — see [common/README.md](common/README.md) |
| `registry.py` | `Registry` — every node lookup (schema, executor, catalog, planner enum) derived from `SPECS` |

## API surface

The routes and how they are guarded: [api/README.md](api/README.md).


