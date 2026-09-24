# BookShelf

An AI book recommender that **plans before it searches**. Instead of routing a
message through a fixed graph, it asks an LLM to turn the message into an
explicit set of goals — each one a typed capability with its own arguments —
shows you that plan as a diagram, then executes it against a Postgres catalog of
5,197 books using vector similarity, full-text search and structured filters.

**[Live demo](https://tuanqpham0921.web.app)** ·
**[Video walkthrough](https://drive.google.com/file/d/1iMLYHvfMU0ECTITtlwgHNjXtJGePy7fE/view?usp=sharing)**

[![CI](https://github.com/tuanqpham0921/Book-Recommender/actions/workflows/ci.yml/badge.svg)](https://github.com/tuanqpham0921/Book-Recommender/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

```
"Find horror novels similar to It by Stephen King"
"Books like Dune but under 300 pages"
"Compare Dune and The Iliad based on themes and complexity"
"I want something philosophical but easy to read"
```

---

## How it works

Three layers, each visible in the trace the UI renders:

| Layer | Question it answers |
|---|---|
| **Triage** | Is this worth planning at all — small talk, out of scope, or a real ask? |
| **PlanJane** | What are the goals? Emits typed goals from a tool catalog built out of the node registry, plus the Mermaid diagram you see before execution |
| **TaskRunner** | Runs each goal against its executor, streaming one collapsible section per step |

Retrieval is **counts-first**: a node builds a query and counts it without
fetching rows, so "2,429 books → 250 → 49" costs three `COUNT`s, not three
result sets. Only a small preview is ever materialized. After every goal has
run, one writing stage turns the results into prose with book cards attached to
the paragraphs that mention them.

The full architecture — node taxonomy, the vertical-slice layout, the tracing
library (`airglider`) — is in **[CLAUDE.md](CLAUDE.md)** and
**[docs/](docs/README.md)**.

---

## Live deployment

| Piece | Where | Deploy with |
|---|---|---|
| Frontend | Firebase Hosting — [tuanqpham0921.web.app](https://tuanqpham0921.web.app) | `make -C frontend deploy` |
| Backend | Cloud Run `book-shelf-api`, `us-east5` | `make -C backend deploy` |
| Database | [Neon](https://neon.com) — managed Postgres 18 + pgvector, `aws-us-east-2` | `make -C backend neon-bootstrap` |

Both deploy commands are self-contained: the backend recipe in
[`backend/Makefile`](backend/Makefile) carries every flag of the live revision
(CPU, concurrency, startup probe, service account, env), and the frontend's API
URL lives in `frontend/.env.production`, so a fresh clone builds a bundle that
points at the real backend. Secrets are **not** in either: the OpenAI key and
the database password come from Secret Manager at runtime.

Runbooks: [docs/deployment.md](docs/deployment.md) (Cloud Run, staged) and
[docs/deployment-neon.md](docs/deployment-neon.md) (the database).

---

## Quick start

**Prerequisites:** Python 3.12 + [Poetry](https://python-poetry.org), Node 22+,
Docker (for the local Postgres), an OpenAI API key.

### Backend

```bash
cd backend
poetry install
cp config/.env.example config/.env   # then fill in OPENAI_API_KEY + POSTGRES_PASSWORD

make postgres-start                  # Postgres 16 + pgvector; db/init/ builds the schema
make dev                             # http://localhost:8000
```

The catalog itself is **not in the repo** — a dump of 5,197 books with their
1024-dimension embeddings is ~67 MB, so `data/*.csv` and `data/backup/` are
git-ignored. Two ways to get rows:

- `make postgres-restore BACKUP_FILE=path/to/your.sql` — replay a dump you have.
- `make dev-neon` — skip local data entirely and run the same server against the
  Neon database, by layering `config/.env.neon` over `config/.env`.

### Frontend

```bash
cd frontend
npm install
make dev                             # http://localhost:3000, talks to :8000
```

No env file to create: `.env.development` already points at the local backend.
To override it, add a git-ignored `.env.local`.

### Tests

```bash
make -C backend tests-all            # unit + integration + the airglider library
make -C frontend lint                # ESLint
```

Integration tests run the real FastAPI app over an ASGI transport with the
stores faked, so they need no database and no OpenAI key. CI runs both suites
plus a production frontend build on every push.

---

## Project structure

```
backend/
  app/
    api/            FastAPI routes and request/response schemas
    common/         messages, SSE stream, RequestContext
    domains/        one folder per capability (vertical slices) + the book domain
    orchestration/  Orchestrator, Triage, TaskRunner, run recorder
    registry.py     the node registry — every lookup answers from SPECS
  airglider/        standalone tracing/result library (own tests, no app imports)
  clients/          OpenAI client, tracing-free by design
  config/           pydantic-settings + constants (.env lives here, git-ignored)
  db/               async engine, SQLAlchemy models, stores, init SQL
  evals/            planner suites, runner and reports; the triage decomposition eval
  Dockerfile        what Cloud Run builds
frontend/
  src/
    api.js          the only backend surface
    components/     chat, book cards, mermaid diagram, review queue
    pages/          BookShelfPage (shell), ChatReviewPage
    design-system/  buttons, modals, dropdowns
  public/blog-posts/  static markdown for the /blog view
docs/               roadmap, backlog, eval strategy, design records, runbooks
```

---

## Status

Public pre-release. Conversation is single-turn: each message is planned and
answered statelessly. What is deliberately not done yet — an auth gate on the
review endpoints, turning run recording back on in production, rate limiting —
is tracked in [docs/backlog.md](docs/backlog.md) and Stage 4 of
[docs/deployment.md](docs/deployment.md).

---

## License

MIT — see [LICENSE](LICENSE). Feedback welcome: tuanqpham0921@gmail.com
