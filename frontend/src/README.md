# frontend/src

Single-page React app (React 19 + Vite). All routes (`/`, `/blog`, `/review`) render
`BookRecommenderPage`, which maps the path to a view; views are lazy-loaded and stay
mounted once visited.

## Map

| Path | What it is |
|---|---|
| `api.js` | **The only backend surface.** Uses `VITE_API_URL`; wraps fetch with a 120s timeout. Note: `stopChatStream`, `getTaskPlanDiagram`, and `getRecommendedBooks` are dead/unwired (docs/backlog.md) |
| `components/ChatBot.jsx` | Chat view: sends messages, consumes the SSE stream, builds ordered response sections (`text`/`books`/`diagram`/`error`/`task`) in `use-immer` state |
| `components/chatbot/` | `ChatInput`, `ChatMessages` (react-markdown + remark-gfm rendering), `TaskSection` (one collapsible executed node) |
| `components/MermaidDiagram.jsx` | Renders the task-plan diagram (`securityLevel: 'strict'`, pan/zoom via `@panzoom/panzoom`); shared with the review page |
| `components/book/` | `BookCard`, `BookCover`, `BookDetailModal`, `BooksGrid` |
| `pages/ChatReviewPage.jsx` | Review queue over recorded chat runs: expand a run → goals, goal diagram, raw envelopes; file one review per run (`PUT /feedback/review`). The diagram is read out of the `planner` JSONB envelope (`output.diagram`), not the promoted `mermaid` column. The second "parsed arguments" diagram was dropped on 2026-08-10 when PlanJane became the only backend renderer — it had also been reading the wrong envelope, so it never displayed |
| `pages/BookRecommenderPage.jsx` | Shell: header, view switching |
| `design-system/` | Button, Badge, Modal, Dropdown, IconButton, ColorModeToggle, … |
| `hooks/`, `utils/`, `styles/`, `data/` | Support code; split CSS lives in `styles/` |

## SSE events the chat handles

`chat.id`, `ui.loading`, `content.delta`, `book_card`, `mermaid.diagram`,
`task.start`, `task.end`, `step.complete`, `error`, `complete` — handled in
`ChatBot.jsx` via `parseSSEStream` from `utils/`.

**`book_card.data` is pinned by `BookOut`** (`backend/app/api/schemas/external.py`):
`isbn13`, `title`, `authors`, `categories`, `published_year`, `num_pages`,
`average_rating`, `description`, `thumbnail`. That is the whole payload — the
backend's internal `Book` model carries more catalog columns, and they are
dropped at this boundary rather than shipped and ignored. A component reading
a field outside that list gets `undefined`, so adding one means adding it to
`BookOut` too.

**Sections are flat except for tasks.** `task.start` / `task.end` bracket one
executed node, and `content.delta` / `book_card` arriving between them nest
inside that task's own `sections` list (`openContainer()` in `ChatBot.jsx`)
rather than landing at the top level. That is the one level of nesting in the
tree — a task holds text and books, never another task — so `renderSection()`
in `ChatMessages.jsx` recurses exactly once. The plan diagram is streamed
before any task opens, which is why it stays outside them.

The pair is emitted by `TaskRunnerWorkflow`, not by individual executors, and
closed in a `finally` — a node that raises still closes its section. `task.end`
carries the `count` that stamps the header after the fact, since a section opens
before the node knows how many books it matched. Sections open expanded and fold
themselves on `task.end`, so the finished turn shows the answer rather than the
work; `collapsible: false` stays open, and a user click pins the state.

**A section stays open when it carries prose.** Every other node's cards are
working material, and the prose written from them is what the turn is for — so
those sections fold and the ones carrying a reply stay open. Two things set
`collapsible: false`, and the backend ands them: the executor class (the
similarity node always writes, so its section never folds) and the *dispatch*
(since 2026-09-09, a goal the planner asked to answer in words — "do you have
Dune?" — opens the section of whichever node answers it, `Retrieve_by_Title`
today). It was briefly a separate `Generate_Recommendations` section (2026-09-07
to 2026-09-08); that node was deleted.

A plain lookup nobody asked to speak still folds everything and gets no prose,
which is intended — it is a step in someone else's chain. What is still a real
gap rather than a styling choice: a goal that *fails* opens no section at all,
so nothing explains it. See `backend/app/orchestration/task_runner.py` and
`docs/design/execution-pipeline-v1.md`.

## Conventions

- Complex nested state uses `use-immer`.
- Review categories in `ChatReviewPage.jsx` must match the backend's
  `FeedbackCategory` literal (`backend/app/api/schemas/external.py`).
- Reduce features rather than add them — V1 direction (docs/roadmap.md).
