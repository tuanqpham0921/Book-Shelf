# frontend/src

`frontend/src` is the code of BookShelf's React app. Every route (`/`, `/bookshelf`, `/airglider`, `/planjane`, `/review`) renders `BookShelfPage`, which maps the path to a view: the chat, one about page each, or the review queue. Views load lazily and stay mounted once visited.

| Path | What it is |
|---|---|
| `api.js` | every backend call, one function per endpoint; a 120s timeout, plus the App Check header in production |
| `utils.js` | `parseSSEStream`, which turns the chat response into events |
| `components/ChatBot.jsx` | the chat: sends a message and builds the turn's sections from the stream |
| `components/chatbot/` | the input box, the message list, each step's collapsible `TaskSection`, and `ChatFeedback` (thumbs, comments, the turn's log and its sources) |
| `components/book/` | book cards, covers, the detail modal and the grid |
| `components/DisplayPanel.jsx` | picks the view for the path, loads it lazily and keeps it mounted |
| `components/MermaidDiagram.jsx` | the plan diagram, shared with the review page |
| `components/BlogPost.jsx` | the about pages: markdown from `public/about/<page>/README.md`, with no header of its own |
| `pages/ChatReviewPage.jsx` | the review queue over recorded turns, one review per turn |
| `design-system/` | buttons, badges, modals, dropdowns, the color-mode toggle and `CodeBlock` |
| `data/` | the chat's suggested prompts and the feedback categories |
| `styles/` | the CSS, split by area; colors are tokens in `tokens.css` |

The backend doesn't serve the review routes in production, so `/review` works only against a local backend (`make dev-neon` in `backend/`). The chat's own feedback works everywhere.

## How a turn renders

`ChatBot.jsx` reads these SSE events: `chat.id`, `ui.loading`, `content.delta`, `book_card`, `mermaid.diagram`, `task.start`, `task.end`, `sources`, `step.complete`, `error`, `complete`. It turns them into a list of sections, `text`, `books`, `diagram`, `error` or `task`, kept in `use-immer` state.

```
turn
├─ diagram            the plan, drawn as the first step, starts open
├─ task               one per goal, starts folded
│  ├─ details         args, SQL, cost (from task.end)
│  └─ text / books    "Preview · N of M books"
└─ text / books       the reply, always open (collapsible: false)
```

- **Tasks are the only nesting.** `task.start` and `task.end` bracket one goal, and anything streamed between them lands in that task's `sections`. A task never holds another task, so `renderSection()` in `ChatMessages.jsx` recurses once.
- **`task.start`'s title is the goal's instruction.** `task.end` brings the book count for the header, plus `details`: the parsed `args`, `sql`, `error_message`, duration and tokens. `TaskSection` shows those first, then the preview cards.
- **The reply is the turn's answer, so it stays open.** Every step folds, so the turn shows the answer rather than the work.
- **`sources`** follows a reply that drew on project facts. The Sources button beside the log button opens them.
- **`complete`** carries the turn's flattened trace, which the log button shows. A crashed step's error arrives as its type and message only; the traceback stays on the server (`browser_record` in `run_recorder.py`).

**A book card shows only what `BookOut` sends** ([backend/app/api/schemas/external.py](../../backend/app/api/schemas/external.py)). A field outside it is `undefined` here, so showing a new one means adding it to `BookOut` first.

## Conventions

- Nested state uses `use-immer`.
- Backend calls go through `api.js` and nowhere else.
- `data/feedbackCategories.js` must match the backend's `FeedbackCategory`.
