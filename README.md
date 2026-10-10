# BookShelf
intro (why, demo link)

To set up dev
- to frontend README
- to backend README



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
  public/about/       static markdown for the about pages (/bookshelf, /airglider, /planjane)
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
