# Backlog

**Updated:** 2026-10-08 · Checked against the code on that date: fixed items were
removed, not struck through.

Tiers: **P1** before or with the V1 ship, **P2** post-V1 candidates, **P3**
someday/cleanup. File and symbol names are the stable part of a reference; line numbers
drift. The `TODO.md` files in `backend/` and `frontend/` are scratchpads; anything worth
keeping graduates here.

## Project info (P1)

From the 2026-10-08 token audit of `Retrieve_Project_Info`. Accounting is correct — no
double counting, and a rejected lookup is charged once — but:

- **A rejection pays twice.** A rejected lookup in triage sends the whole message to the
  planner, which usually routes back to `Retrieve_Project_Info`: a second search and a
  second check that rejects again, plus the planner call. Send triage's rejection straight
  to the reply instead; keep the fall-through only for a lookup that *errored*.
- **Each lookup sends ~7.5k input tokens,** almost all of it chunks (a live `/query`
  returned 28,921 characters). Nothing caps them. Cheap in dollars, but the session
  budget counts tokens. Return fewer chunks (`OpenAIConstants.VECTOR_STORE_MAX_RESULTS`) or cap their length in
  `search_project_docs`.
- **The reply sees the triage lookup as free.** `Orchestrator` builds its `TaskResult`
  with no duration or tokens, so the writer's `<info>` has no cost line for it. Billing is
  unaffected. Carry the lookup record's stats onto `TriageOutput`.
- **P3:** the `MAX_COMPLETION_TOKENS` comment in `find_project_info/executor.py` mentions
  reasoning tokens, but effort is `none`. The cap (4,000) could come down.

## Security & pre-deploy (P1)

- **The review surface has no auth.** `GET /chat_runs`, `GET /feedback` and
  `PUT /feedback/review` take no credential and no ownership check. They are **not
  served in production**, which closes the disclosure; this stays open only if the review
  page should ever go public (an admin gate — [deployment.md](deployment.md) §4.1).
- **`uuid_8()` is 32 bits** (`airglider/src/utils.py`). It is the primary key for
  `chat_runs.chat_id` and `feedback.id`: ~1% collision odds at ~9,300 rows, 50% at ~77k.
  A collision loses one record, not a reply. A one-line change in airglider.
- **The 2,000-character message limit is a literal in the route**
  (`app/api/routes/chat_message.py`). Move it onto `ChatIn.message` as a `Field`, with the
  bound in `config/constants.py`.

## Reliability (P1)

- **OpenAI rate limits under concurrent load.** Concurrent suite runs have tripped the
  tokens-per-minute limit. Options: (1) surface a "rate limited, try again" reply;
  (2) backoff and retry on the client (see Workflow framework, item 5); (3) a higher
  OpenAI tier. Capacity arithmetic: a turn is roughly 10–15 requests (check, router,
  planner, one parse per node, reply), so the 500 RPM tier is ~30 concurrent turns before
  throttling, fewer in bursts. The next tier removes the pressure, which makes (3) the
  cheap answer.
- **Garbage-collected pool connections.** Suite runs logged `SAWarning: The garbage
  collector is trying to clean up non-checked-in connection`. This predates per-use
  sessions (`ctx.store`, which commits and closes on exit) and may be gone. Check a suite
  run's log; the remaining suspects are the `session_factory()` calls in
  `evals/common.py` and `evals/planjane/run_suites.py`.

## Planner & routing quality (P2)

- **Session questions have no answer.** "How many messages do I have left?" reaches the
  planner, which has no node for it.
- **Prompt injection still reaches node arguments and the writer.** The message check and
  triage's `SecurityReview` stop clear misuse, but triage fails open, and the reply
  writer reads the user's whole message. A node's parsed arguments are where an injected
  string actually lands; they need their own tests.
- **`Retrieve_by_Title` should prefer exact matches.** `title_query` keeps every row where
  `title ILIKE '<t>'` **or** trigram similarity > 0.7, so several editions of one book all
  match. As an anchor, six editions trip `Analyze_Similar_Books`' `MAX_ANCHOR_BOOKS` (5)
  and fail "books like X". Fix in `title_query` (exact arm first, trigram only when it
  finds nothing), which fixes every consumer at once.
- **`confidence` sometimes comes back 0.0.** `planjane/executor.py` rejects goals below
  the threshold, so a spurious 0.0 silently drops a good goal. Unknown whether the model is
  unsure, omits the field, or anchors on an example. The two causes want opposite fixes;
  check recorded runs before tuning the threshold.
- **Embedding experiments:** how closely do single-word genre or author embeddings score
  against near misses? Could a composed record embedding answer "books with 100 pages"?
- **P3 — no worked example of analyze depending on analyze.** Add one when the analyze
  tier grows past one node.
- **P3 — first-person `reasoning`.** Friendlier if it ever reaches the UI, but only safe
  while the field stays display-only; first-person text is a worse input to a re-parse.

## Node contracts & refusal (P2)

Written up in [design/node-refusal-v1.md](design/node-refusal-v1.md):

- **The args parser cannot decline.** A single tool model pins `tool_choice`, so a
  mis-routed goal parses anyway ("a book about war" → `title="war"`) and finalizes ok.
- **A 0-count result is ok for the producer and empty for the consumer.** The similarity
  node handles it; the general fix is skipping a node whose dependencies are all empty.

## Correctness (P2)

- **The review page can't tell a crash from a child failure.** It keys off one flat
  `run.planner?.runtime_error`. An unhandled exception and a child step's `StepFailure`
  stamp the same field, so they render identically. Needs an error-kind field from the
  backend, or at least a distinct label derived from the traceback.
- **Investigate the semaphore** (`OpenAIClient.semaphore`, `OPENAI_MAX_CONCURRENCY`) —
  a concurrency issue was seen during suite runs. Try a lower limit and observe.

## Performance (P2)

- **Per-character SSE streaming.** `SSEStream.send_chars` sends one event plus an
  `asyncio.sleep` per character, for every reply paragraph. Chunk by word if latency
  becomes a complaint.
- **Dead `index=True` flags** on `BookModel` (`db/schema/models.py`). Indexes come from
  the SQL in `db/init/`, so the flags do nothing, and `published_year`, `average_rating`
  and `genre` filters run unindexed. Add real indexes or drop the flags.
- **One round trip per count.** Several retrieval goals run several `COUNT`s. They could
  be one statement over counted CTEs. Worth measuring now that intersect plans are common.

## Tracing, clients & tooling (P2)

- **A compact tracer mode.** A run's JSONB carries every step's input and output. A mode
  that flattens the tree or keeps only identifying fields (isbn13 + title) would help eval
  review and bulk reads.
- **`add_details(msg, log=True)`.** Details go to the record only, so anything worth seeing
  live is logged separately and the two drift. Open question: which details deserve a log
  line without eroding the split (logs = start/fail/end, details = the pipeline).
- **Delete the unused streaming path.** Every LLM call now goes through
  `client.responses.create`; `OpenAIChatRequest` and `OpenAIClient._chat_stream`
  (`client.beta.chat.completions.stream`) have no caller in `app/`, and nothing in `app/`
  sets `BaseLLMRequest.sse_stream`. Removing them lets that field and its `SSEStream`
  import go too — the last app coupling in `clients/`.

## Test coverage (P2)

- **Stores:** no tests for `chat_run_store.py` or `feedback_store.py`.
- **Routes:** `session.py` and `health.py` have no tests.
- **Untested modules:** `common/context.py`, `db/async_engine.py` (the timeout layers).
- **Concurrency and timeouts:** the semaphore and the workflow timeouts.
- **Frontend:** no tests. Priorities: markdown rendering edge cases, error messages,
  backend down or stalling.

## Workflow framework (P2)

These need design, not drive-by fixes:

1. One executor for `@task` and `Workflow` (unify the two call paths).
2. Timeouts inside `@task` and `Workflow` themselves.
3. **Checkpoint gap.** A child is attached to its parent only when it finishes
   (`parent_scope` attaches in `finally`), so interrupted child progress is lost. Better
   checkpointing needs incremental attachment and a rethink of append/overwrite
   semantics. Blocker 1 for [design/human-in-the-loop.md](design/human-in-the-loop.md).
4. **Is `@task` idempotent?** A step that runs twice may report a duration measured from
   the wrong start. Matters for retries and resume; worth a test before either is built.
5. **Retries.** No retry exists in `app/`, `clients/`, `airglider/` or `config/`; the only
   one is the OpenAI SDK's default (`max_retries=2`, transport errors), and `AsyncOpenAI`
   sets no client timeout. A *business* retry (parse → post-process → store) should be its
   own envelope per attempt, and the **parent** decides the re-write — a node that failed
   to parse should not be the one that rewords the query.

Once resume exists, DAG processing may move into model validation so the orchestrator
can pick up and continue.

## Accessibility (P2)

- Version and category dropdowns (`design-system/Dropdown.jsx`, `VersionDropdown.jsx`):
  mouse-only, no Escape, no `aria-haspopup`.
- NavBar overlay: closes on click only — no keyboard path, focus trap or Escape.
- Chat textarea: its accessible name is the placeholder, which disappears once typing
  starts. Add an `aria-label`.

## Frontend cleanup (P3)

- `formatAuthors` / `formatAuthorsMobile` (`utils/bookUtils`) are near-duplicates;
  collapse them with a `compact` flag.

## UI polish pool (P2/P3)

- Scrollable sidebars; chat input scrolls on first input.
- Mermaid: viewport minimum height; long or wide graphs could wrap into rows. Does the
  fixed 14px font scale on small devices, and is `user-scalable=no` still needed?
- Review page: align the preview; put praise/issue controls next to submit for a top-down
  flow; consolidate feedback, hints and colours into one area.
- Book cards: edge-triggered horizontal auto-scroll, and lift on hover.

## Ideas pool (P3 — not scheduled)

Kept so the reasoning isn't re-derived.

- **A "why?" button on a card.** The card knows its isbn13, so it could call an analyze
  node directly, with no planner — a fixed capability with a fixed input needs no plan.
  The cheapest form of multi-turn: continuing a turn without reopening the conversation.
- **Analyze nodes that call the planner themselves** for the retrieval they need. A node
  knows its own gaps, but "recommend like A and B, then compare A and B" becomes two
  planner calls over the same books. An entity cache would be the prerequisite. Related to
  [design/planner-shape.md](design/planner-shape.md) experiment 4.
- **A bounded multi-turn loop:** plan → run → reword, capped at ~10 goals per iteration,
  with an internal summary at the end. Wants V1.1 conversation first, and nothing may stay
  alive between iterations ([design/human-in-the-loop.md](design/human-in-the-loop.md)).
- **A narration line per unit of work** ("searched similar books with …, took 10s, N
  tokens"). May just be a function over the record, written where it is needed.
- **Pre-made plans for common shapes** ("find title → similar books", the bare
  "recommend me something"). Same idea as branching inside a node; does nothing for the
  slow half (embedding), which isn't cacheable across queries.
- **A unified artifact renderer.** Mermaid is the only thing the app renders *about* a
  run. A name + description + body shape would let any node hand the UI a comparison
  table or an ideal-book description without its own SSE event.

## Settled — recorded so they aren't re-opened

- **A unit of work opens its own database session** (`ctx.store(...)`, per use), rather
  than sharing one per request. The turn outlives the HTTP handler, so a request-scoped
  session would already be closed.
- **Each node parses its own arguments in its own call**, not one combined parse. It
  costs more requests and buys per-node prompts and models, plus a parse that never runs
  when an upstream goal fails.
- **Numeric bounds are a retrieval, composed by `Combine_Intersect`,** not a filter after
  the search. `compose(op="and")` carries the similarity score through, so ranking
  survives the narrowing.
- **The similarity floor is `MIN_SIMILARITY = 0.35` with a 250-book pool cap**
  (`config/constants.py`, `find_similar_books/executor.py`).
- **The reply is one unregistered stage per turn**, not a node the planner picks
  ([design/execution-pipeline-v1.md](design/execution-pipeline-v1.md)).
