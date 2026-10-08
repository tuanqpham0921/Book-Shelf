# V1 node taxonomy (decision record)

**Updated:** 2026-10-08 · **Status:** accepted. Seven nodes are registered; the rest of
the V1 set is designed but not built.

This records which capabilities the planner can pick, the rules that shape them, and why.
`make tools-catalog` prints what is actually live, with per-tool token costs; trust it
over this file if they disagree. How the nodes run once picked is in
[execution-pipeline-v1.md](execution-pipeline-v1.md).

## The node set

### Registered

| Node type | Slice | Tier | Output shape |
|---|---|---|---|
| `Retrieve_by_Title` | `books/find_by_title/` | Retrieval | `BookAnchorOutput` |
| `Retrieve_by_Author` | `books/find_by_author/` | Retrieval | `BookCandidateOutput` |
| `Retrieve_by_Lexical_Traits` | `books/find_by_lexical_traits/` | Retrieval | `BookCandidateOutput` |
| `Retrieve_by_Numeric_Traits` | `books/find_by_numeric_traits/` | Retrieval | `BookCandidateOutput` |
| `Analyze_Similar_Books` | `books/find_similar_books/` | Analyze | `BookCandidateOutput` (scored) |
| `Combine_Intersect` | `books/intersect_books/` | Combine | `BookRetrievalOutput` |
| `Retrieve_Project_Info` | `project/find_project_info/` | Retrieval | `ProjectInfoOutput` (not book-shaped) |

The catalog is 7 tools and about 3,100 tokens, sent to the planner on every request.

### Designed, not built

| Node type | What it would do |
|---|---|
| `Retrieve_by_ISBN13` | Exact ISBN lookup. Anchor-shaped |
| `Retrieve_by_CoAuthors` | Joint works only: 2+ authors ANDed onto the same book. The one multi-value node |
| `Retrieve_Random` | One arbitrary pick, with an optional `BooksFilter`, for the bare "recommend me a book" |
| `Combine_Union` | Explicit OR over several inputs, for when a pooled set is itself a step |
| `Analyze_Compare` | Compare books; waits on a single-book analyze node (see Future considerations) |

There is no generate tier. The turn's reply is written by a stage that runs after every
plan, not by a node the planner picks (see
[execution-pipeline-v1.md](execution-pipeline-v1.md)).

## Rules every node follows

**One dimension, one value.** Each retrieval node searches one thing: one title, one
author. Several authors' separate bibliographies are several `Retrieve_by_Author` goals,
not one goal with a list. Cross-dimension asks ("horror by King over 500 pages") are
built by composition: one retrieval per dimension, joined by `Combine_Intersect`. The
combine tier is the only place a plan says "and".

**Two documented exceptions, both because their subject has no single dimension:**

- `Retrieve_by_Numeric_Traits` carries a whole `BookMetadataFilter` (rating, ratings
  count, pages, year). The bounds are always the *subject* of its search ("books under 200
  pages"). A bound beside another subject is this node plus `Combine_Intersect`.
- `Retrieve_by_Lexical_Traits` carries subject keywords, fiction-ness and audience,
  ANDed, because "non-fiction about history" is one question, not two to intersect.

**Pooling is implicit.** Several task ids in one `depends_on` mean "pool what all of
these found" (OR). That is why emitting a subject goal and a numeric goal *without* an
intersect answers with more books, not fewer — the trap both docstrings warn about.

**The request schema is fieldless.** The planner sees a docstring and a `node_type`
Literal, nothing else. The arguments live on a plain `*Args` model in the slice's
`tools.py`, which only the node's own parse call sees. No filter object sits on any
planner-facing schema.

**`unknown` is a member of `NodeTypeEnum`,** so the planner can decline a goal instead of
picking a wrong capability.

## Anchors vs candidates

`BookRetrievalOutput` has two subclasses in `books/external.py`, and neither adds a field:

- **`BookAnchorOutput`** — the user *named* these books (`Retrieve_by_Title`, and
  `Retrieve_by_ISBN13` when built).
- **`BookCandidateOutput`** — these books match a *description* (`Retrieve_by_Author`,
  `Retrieve_by_Lexical_Traits`, `Retrieve_by_Numeric_Traits`, and the similarity pool).

`build_input` fills fields by `isinstance`, so the type is the payload. A node declaring
`list[BookAnchorOutput]` cannot be handed a 358-book subject search; the runner skips the
goal and names the field instead.

- **The criterion is *named*, not *small*.** A title search can still match several
  editions, so consumers that fold anchors still need a cap.
- **`Retrieve_by_Author` is a candidate** because the node cannot tell twelve books from
  eight hundred. The cost: "books like Frank Herbert's" cannot anchor on a bibliography.
- **The base class stays concrete.** It means "either, and not anchorable".
  `CombineIntersectOutput` lands on it because an intersection of two titles is
  anchor-shaped and one of two subject searches is not, and the class cannot know which.
  A node that wants both writes `list[BookAnchorOutput | BookCandidateOutput]`, which
  rejects a bare base instance.
- **No pydantic discriminated union.** `_resolve` calls `isinstance`, and a subscripted
  generic raises there. The class already is the discriminator.

**Known wart:** when a plan sends both an anchor and a candidate to a
`list[BookAnchorOutput]` field, `build_input` drops the candidate with a `logger.debug`
line, and the node never learns it. Raising the log level is the cheap fix.

## Per-node notes

### `Retrieve_by_Numeric_Traits`

- **Superlatives become bounds, not ordering.** "Highest rated" becomes `min_rating: 4.3`.
  The node emits no `score`, so results fall back to `average_rating DESC` — right for
  "well rated", wrong for "the longest books". Emitting the named trait as `score` is the
  one-line fix if evals ask for it.
- **Vague words are inferred; nothing is invented.** "Well rated", "obscure", "something
  long" must become numbers, so the slice has its own parse prompt (the shared one says
  "do not infer"). But a mis-routed goal ("a book about dragons") must parse to an empty
  filter and fail, not invent bounds. The executor raises on an empty filter.
- **gpt-5-nano at effort `low`.** At `minimal` it scored 2/8 on a calibration set and
  corrupted output; at `low`, 8/8. gpt-5-mini added nothing.
- **Calibration lives on `BookMetadataFilter`'s field descriptions,** so any future
  consumer of the model reads "well rated" the same way.
- `BookMetadataFilter` validates its ranges (no negative pages, no inverted ranges).
  `min_year`/`max_year` take no upper bound: the catalog ending in 2019 is a fact about
  the data, so "published after 2020" is a real question whose answer is zero.

### `Retrieve_by_Lexical_Traits`

- **Lexical, not semantic.** It asks whether the catalog's text *contains these words* —
  a full-text `tsquery` over title, shelf label and blurb — and hands on a composable
  query over the whole match. `Analyze_Similar_Books` asks which books are *near an
  embedding*. "Cozy mysteries" is this node alone, with *cozy* dropped: the similarity
  node takes only named books.
- **Full-text search, not ILIKE.** It stems ("ninjas" finds "ninja") and respects word
  boundaries: `ILIKE '%war%'` matches 985 books including "toward"; the tsquery matches 442.
- **The genre trap.** `books.genre` holds four values, and `genre ILIKE '%Fiction'`
  matches all of them, because "Nonfiction" ends in "fiction". Genre and audience are
  exact set membership, never a pattern.
- **`is_children` is a dead column** (NULL on all 5,197 rows). Audience resolves against
  `books.genre` instead. `BookMetadataFilter.is_children` still exists and matches
  nothing; the fix is deleting it.
- **The GIN index is fragile.** `books_search_idx` takes the query from ~520ms to ~5ms.
  Two innocent-looking changes disable it: passing `'english'` as a bound parameter, and
  using `concat_ws` (STABLE, not IMMUTABLE). The expression is written twice (in
  `search_document()` and in the DDL); `tests/unit/db/stores/test_lexical_query.py`
  checks that the two match and that no parameters are bound.

### `Analyze_Similar_Books`

- **One job:** pool the anchor books, fold them into one ideal-book description (one LLM
  call, gpt-5-mini), embed it, and hand on the 250 nearest as a scored
  `DeferredBookQuery`, nearest first. It does not rank, exclude or write a reply.
- **Anchors only, by type.** `SimilarBooksInput.anchors` is
  `list[BookAnchorOutput]` with `min_length=1`.
- **Blend vs separate is decided by the plan.** "Books like X **and** Y" is one goal with
  two `depends_on`; "like X **or** like Y" is two goals. The docstring says so; nothing
  enforces it.
- **`MAX_ANCHOR_BOOKS` is 5,** and the node raises past it rather than folding the top 5,
  which would answer confidently from a sample nobody chose. Six editions of one title can
  trip it; the fix belongs in `title_query` (see [backlog.md](../backlog.md)).
- 0-count anchors are kept out of the pool (`ParsedDependents.empty`), and the node raises
  when nothing is left to be similar to.

### `Combine_Intersect`

- **No LLM call.** Its dependencies decide everything; `build_input` is its whole parse.
- **N-ary, `min_length=2`.** One retrieval per condition, all feeding one intersect. An
  intersection of one would report the upstream count as if something had narrowed it.
- **One score survives.** `compose(op="and")` carries `score` through when exactly one
  input has one, so "books like Dune under 300 pages" stays in cosine order.
- **Its output is the base `BookRetrievalOutput`,** so `Analyze_Similar_Books` cannot
  depend on it. "Books like Harry Potter by Rowling" anchors on the title retrieval.
- **It cannot say "of the 250 nearest, N also match".** Detecting a truncated similarity
  pool would mean importing across a slice seam, so the caveat stays in the docs.

### `Retrieve_Project_Info`

Answers questions about BookShelf itself, in two steps:

1. `search_project_docs` (a `@task`) POSTs the instruction to `/query` on the project-docs
   RAG service (`settings.app.PROJECT_DOCS_URL`) and gets the ten closest chunks.
2. One LLM call fills `ProjectDocsAnswer` (`supported`, `sources`, `answer`) from those
   chunks alone. `supported` is decided first; when it is false the node **rejects**
   (empty answer, not ok) instead of answering anyway. An empty `answer` alone was too
   weak a signal: the model blanked real answers and filled in non-answers.

There is no arg parse and no store, so the executor subclasses `AppWorkflow` directly.
Most project questions never reach this node through the planner: triage's router is
offered `ProjectInfoArgs` and runs the executor itself as a child workflow, carrying the
output on `TriageOutput.project_info`. A rejected or failed lookup in triage sends the
whole message to the planner. The node stays registered as the planner's route to the
same facts.

**The service runs locally only.** In production every lookup fails, so project
questions fall through to the planner, whose node fails too. See
[backlog.md](../backlog.md).

## Output shapes

`Book` is the single book model — every `books` column except `embedding` (a per-book
vector would bloat every `chat_runs` row). There is deliberately no narrower model:
narrow at the point of use (a renderer picking fields, `model_dump(include=...)`).

`BookRetrievalOutput` carries `num_books`, `query` (the composable deferred query,
excluded from serialization), `query_sql`, and `preview` — the first `default_limit` (4)
rows the node fetched for its cards. `preview` is kept for the turn's record and the
reply; it is never an input to another node.

## V1 conversation contract

- **Single-turn.** Each message stands alone. Turns are recorded to `chat_runs` but never
  read back. Multi-turn is the V1.1 flagship.
- **Unclear or misused input is answered, not silently shrunk.** The message check
  (`orchestration/validation/`) refuses harmful, misused or gibberish messages. Triage's
  router turns away misuse (`SecurityReview`) and asks for clarification
  (`ClarifyingQuestion`) when a message cannot be acted on — including a follow-up with
  no earlier turn. The planner's `out_of_scope` portions reach the reply as "not
  something BookShelf does".
- **Still open:** goals the planner *refuses* get no reply of their own (TODO in
  `planjane/executor.py`). A turn where every goal is refused ends in the orchestrator's
  generic error.
- **The system can only answer what a `books` row holds:** author, year, pages, rating,
  shelf, genre, and a marketing blurb. "Who wrote Dune" is answerable; "who is the main
  character" is not. Nothing in the schema knows what happens inside a book, and a
  retrieval node will happily match the words and answer confidently anyway.

## Future considerations

- **Compare.** There are two kinds. *Compare for information* ("which is longer, Dune or
  IT?") is the answer itself. *Compare to pick a winner* ("books like whichever is
  shorter") feeds a later goal, and only that kind needs a dependency contract. The
  winner need not travel as a book: "Dune is 100 pages longer, so it wins" gives the next
  goal a title to anchor on. The comparison must be on metadata, not themes — the schema
  has nothing to compare themes with. A single-book analyze node is the prerequisite.
- **Book-clamped recommendations.** Attach a recommendation to a successful lookup ("do
  you have Dune? — yes, and you'll like these").
- **Human-in-the-loop re-rank** at the similarity node, when there are many candidates.
  A later use of the machinery in [human-in-the-loop.md](human-in-the-loop.md).
- **An embedding arm for lexical retrieval.** A threshold-only vector query with no
  ORDER BY or LIMIT is a legal `DeferredBookQuery` (~450ms on this catalog), so the
  lexical node could grow a semantic arm that still composes.
