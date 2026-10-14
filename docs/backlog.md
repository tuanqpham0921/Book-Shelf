# Backlog

The BookShelf backlog is a temporary buffer for known bugs and small follow-ups that don't have a home yet. Items here will migrate to GitHub issues and pull requests; once an item is tracked there, remove it from this file.

## Bugs

- [ ] **Escape `%` and `_` in title search** — `title_query` ([book_store.py](../backend/db/stores/book_store.py)) passes the title straight into `ILIKE`, so `%` and `_` act as wildcards (a search for "100%" matches more than it should). Check the other `ilike` builders for the same issue.

- [ ] **`stream_books` crashes on a bad row** — one book that fails `BookOut` validation (e.g. no `isbn13`) raises and stops the remaining cards ([base_workflow.py](../backend/app/domains/books/base_workflow.py)). Skip and log it instead.

- [ ] **`Retrieve_by_Title` should prefer exact matches** — `title_query` keeps every row where `ILIKE` matches **or** trigram similarity > 0.7, so several editions of one book all match. Six editions trip `Analyze_Similar_Books`' `MAX_ANCHOR_BOOKS` (5) and fail "books like X". Try the exact arm first and fall back to trigram only when it finds nothing.

- [ ] **Refused goals get no reply** — a turn whose goals are all refused ends in the orchestrator's generic error (TODO in [planjane/executor.py](../backend/app/domains/planjane/executor.py)).

- [ ] **`confidence` sometimes comes back 0.0** — the planner rejects goals below the threshold, so a spurious 0.0 silently drops a good goal. Check recorded runs for the cause (unsure, omitted, or copying an example) before tuning the threshold; the causes want opposite fixes.

## Project info

- [ ] **A rejection pays twice** — a lookup the docs don't answer in triage sends the whole message to the planner, which usually routes back to `Retrieve_Project_Info` for a second search and a second rejection. Send triage's rejection straight to the reply; keep the fall-through for a lookup that *errored*.
- [ ] **Each lookup sends ~7.5k input tokens**, almost all of it chunks, and the session budget counts them. Return fewer chunks (`VECTOR_STORE_MAX_RESULTS`) or cap their length in `search_project_docs`.
- [ ] **The reply sees triage's lookup as free** — `Orchestrator` builds its `TaskResult` with no duration or tokens, so the writer's `<info>` has no cost line for it. Carry the lookup's stats onto `TriageOutput`.

## Security

- [ ] **`uuid_8()` is 32 bits** (`airglider/src/utils.py`) and keys `chat_runs.chat_id` and `feedback.id`: ~1% collision odds at ~9,300 rows. A collision loses one record, not a reply.
- [ ] **Move the message-length check onto `ChatIn.message`** as a `Field(max_length=AppConfig.MAX_MESSAGE_LENGTH)`; today the route checks it by hand.
- [ ] **Tests for prompt injection in node arguments** — triage fails open and the writer reads the whole message, so a node's parsed arguments are where an injected string lands.
- [ ] **An admin gate for the review routes**, if the review page is ever served in production ([decision 009](decisions/009-no-user-auth-in-v1.md)).
- [ ] **`verify-full` instead of `require`** for the Neon connection ([database strategy](strategies/database.md#open)).

## Reliability

- [ ] **OpenAI rate limits under concurrent load** — concurrent suite runs have tripped the tokens-per-minute limit. A turn is 10–15 requests, so the 500 RPM tier is ~30 concurrent turns. The next tier is the cheap fix; otherwise a "rate limited, try again" reply or client-side backoff.
- [ ] **Garbage-collected pool connections** — older suite runs logged `SAWarning: The garbage collector is trying to clean up non-checked-in connection`. It may be gone since per-use sessions; check a suite log. Remaining suspects: the `session_factory()` calls in `evals/common.py` and `evals/planjane/run_suites.py`.
- [ ] **Investigate the OpenAI semaphore** (`OPENAI_MAX_CONCURRENCY`) — a concurrency issue was seen during suite runs. Try a lower limit.

## Cleanup

- [ ] **A command to load the project-docs vector store** — the store `Retrieve_Project_Info` searches is built by hand from [file_search_docs.ipynb](../backend/evals/app_docs/file_search_docs.ipynb), so a README edit doesn't reach the chatbot until someone re-runs it. Add a make target that uploads the READMEs and `docs/` into the store named by `OPENAI_VECTOR_STORE_ID`.

- [ ] **Remove unused phrase builders** — `describe_bounds` / `range_phrase` (numeric traits) and `describe_lexical_traits` build user-facing lines that nothing shows; they're only used as an "is the parse empty?" check. Replace with a plain check and delete them and their tests.

- [ ] **Name node enums after their classes** — `FindTitleNodeTypeEnum` sits beside `FindByTitle*` (same in `find_by_author`, `find_by_lexical_traits`, `find_by_numeric_traits`). Rename to `FindByTitleNodeTypeEnum` etc. across the book slices.
- [ ] **Move parse model names to config** — every book slice's `build_arg_parser_request` writes `model="gpt-5-nano"` inline; CLAUDE.md says model names belong in `config/constants.py`.
- [ ] **Before extracting airglider** — move `src/` to `src/airglider/` at the package root (or drop the layer); rename `base_glider.py` to match `Workflow`; settle one name for record / `OperationResult` / "envelope"; `exception.py` → `exceptions.py`; give it its own `pyproject.toml` and pytest config (the suite inherits the host's `asyncio_mode = "auto"`).
- [ ] **airglider: retries and typed errors** — retry with backoff, and an error type a caller can branch on (business failure vs crash). A business retry should be its own envelope per attempt, decided by the **parent**. Today the only retry is the OpenAI SDK's default, and `AsyncOpenAI` sets no client timeout.
- [ ] **airglider: `Workflow` sets `ok=True` on clean completion** — today each `run()` sets it (`AppWorkflow.finalize_result`).
- [ ] **airglider: `to_summary()` includes the input summary** — so the summary has everything the full record does.
- [ ] **airglider: incremental checkpoints** — a child attaches to its parent only when it finishes, so an interrupted run loses its partial child work. Blocker 1 for [human-in-the-loop](decisions/010-human-in-the-loop.md). Also check whether a `@task` that runs twice reports the right duration.
- [ ] **airglider: one executor for `@task` and `Workflow`, and timeouts inside both.**
- [ ] **clients: delete the unused streaming path** — `OpenAIChatRequest` and `OpenAIClient._chat_stream` have no caller in `app/`. Removing them lets `BaseLLMRequest.sse_stream` and its `SSEStream` import go too, the last app import in `clients/`.
- [ ] **clients: warn on an unvalidated `UserMessage`** — `to_openai_dict` raises on `pass_validation=False` but says nothing on `None`. Add a warning once it's settled whether planner→node instructions go as user or assistant messages (today they're `AssistantMessage`s, so they wouldn't trip it).
- [ ] **Take dev notes out of docstrings the LLM reads** — `FindByLexicalTraitsArgs` (the "deliberately not `BooksFilter`" paragraph), `BookMetadataFilter` (dates, retired nodes, why the calibration lives there) and `AudienceEnum` ("Db-owned rather than slice-owned") all ship inside tool schemas. Move the notes to code comments and re-run the lexical and numeric eval cases.
- [ ] **Delete `BookMetadataFilter.is_children`** — the column is NULL on every row, so the bound matches nothing.
- [ ] **Dead `index=True` flags** on `BookModel` (`db/schema/models.py`) — indexes come from `db/init/`, so the flags do nothing, and `published_year`, `average_rating` and `genre` filters run unindexed. Add real indexes or drop the flags.
- [ ] **Move pandas to the dev group** — it is never imported at runtime but ships ~100 MB with numpy in the image. It churns `poetry.lock`.
- [ ] **`make tools-catalog`: drop or repoint the schema-token column** — it measures each node's request class as a JSON tool schema, which no call sends (the planner sees only the catalog text). Either drop it or measure the slices' `*Args` schemas, which the node parsers do send.
- [ ] **Collapse `formatAuthors` / `formatAuthorsMobile`** (`frontend/src/utils/bookUtils.js`) into one with a `compact` flag.

## Evals

- [ ] **One eval layout for every node** — give each node in `app/domains/` its own folder in `backend/evals/` with a suite, a runner that calls the node directly, and a report, the way `triage/` and `validation/` already work. Then move `planjane/` onto the same layout.
- [ ] **One make target per eval campaign** — run the suites, dump `chat_runs` with its cascade, and copy the run logs into `evals/results/<name>/` in one step.
- [ ] **PlanJane tests for failed and overflowing goals** — `test_planjane.py` covers accepted goals only; add a refused goal and a plan over `MAX_SYSTEM_GOALS`.
- [ ] **Tune `MIN_SIMILARITY`** (0.35, never tuned) — `score_stats` is the instrument: a pool minimum resting on 0.35 means the floor never binds. Needed before `Combine_Union` ([decision 005](decisions/005-counts-first-retrieval.md)).
- [ ] **ivfflat `lists = 100` is wrong for 5,197 rows** (about 5 is right) — a recall question; changing it changes eval results.

## Tests

- [ ] **Stores:** `chat_run_store.py` and `feedback_store.py` have no tests.
- [ ] **Routes:** `session.py` and `health.py` have no tests.
- [ ] **Modules:** `common/context.py`, and the timeout layers in `db/async_engine.py`.
- [ ] **Concurrency and timeouts:** the OpenAI semaphore and the workflow timeouts.
- [ ] **Frontend:** none yet. Start with markdown edge cases, error messages, and a backend that is down or stalling.

## Performance

- [ ] **Per-character SSE streaming** — `SSEStream.send_chars` sends one event plus an `asyncio.sleep` per character. Chunk by word if latency becomes a complaint.
- [ ] **One round trip per count** — several retrieval goals run several `COUNT`s; one statement over counted CTEs could do it.
- [ ] **`min-instances=1`** would remove the 5–8s first-chat cold start for about $7 a month.

## Tracing and review

- [ ] **The review page can't tell a crash from a child failure** — it keys off one flat `run.planner?.runtime_error`, which both stamp. Needs an error-kind field from the backend.
- [ ] **A compact trace mode** — a run's JSONB carries every step's input and output; a mode keeping only identifying fields (isbn13 + title) would help eval review.
- [ ] **`add_details(msg, log=True)`** — details go to the record only, so anything worth seeing live is logged separately and the two drift.
- [ ] **Continuous deployment** — `.github/workflows/ci.yml` already has the env block it would need.

## Accessibility and UI

- [ ] **Dropdowns** (`design-system/Dropdown.jsx`, `VersionDropdown.jsx`): mouse-only, no Escape, no `aria-haspopup`.
- [ ] **NavBar overlay:** closes on click only; no keyboard path, focus trap or Escape.
- [ ] **Chat textarea:** its accessible name is the placeholder, which disappears once typing starts. Add an `aria-label`.
- [ ] Scrollable sidebars; the chat input scrolls on first input.
- [ ] Mermaid: a minimum viewport height; wrap long graphs; check the fixed 14px font on small screens and whether `user-scalable=no` is still needed.
- [ ] Review page: align the preview, put praise/issue controls next to submit, and gather feedback, hints and colours into one area.
- [ ] Book cards: edge-triggered horizontal auto-scroll, and lift on hover.

## Ideas (not scheduled)

- **Session questions** — "how many messages do I have left?" reaches the planner, which has no node for it.
- **A "why?" button on a card** — the card knows its isbn13, so it could call an analyze node directly with no planner. The cheapest form of multi-turn.
- **Analyze nodes that call the planner themselves** for the retrieval they lack. Needs an entity cache first ([decision 002](decisions/002-capability-nodes.md) on routing inside nodes).
- **A bounded multi-turn loop** — plan → run → reword, capped at ~10 goals per round, with nothing alive between rounds.
- **A narration line per unit of work** ("searched similar books with …, took 10s, N tokens"), as a function over the record.
- **Pre-made plans for common shapes** ("find title → similar books"). Does nothing for embedding, the slow half.
- **A unified artifact renderer** — a name + description + body shape, so any node could hand the UI a table without its own SSE event.
- **Planner experiments:** a typed `purpose` on retrieval goals ("to verify authorship"); whether the planner may infer through contradictory constraints; duplicate goals (rare); domain pre-filtering of the catalog.
- **Embedding experiments:** how single-word genre or author embeddings score against near misses; whether a composed record embedding could answer "books with 100 pages"; a threshold-only vector arm for lexical retrieval that still composes.
- **Carry `max(score)` through a union**, which would fix pooled ranking.
- **First-person `reasoning`** — friendlier in the UI, but a worse input to a re-parse.
