# backend/db

Async SQLAlchemy database layer for PostgreSQL + pgvector.

## Layout

- `async_engine.py` — the shared async engine/session factory. Create sessions from
  here; the engine is closed on app shutdown (don't create ad-hoc engines).
- `schema/` — the Python side of the schema: `models.py` (SQLAlchemy ORM
  models) and `filter_schemas.py`. `Base.metadata.create_all` is *not* how
  tables come to exist — `init/` is — which is why `index=True` flags on models
  do nothing (docs/backlog.md, Performance).
- `init/` — the schema as **raw SQL, run in name order**: extensions → tables →
  indexes. **Not in the image and never read by the app** (`.dockerignore` /
  `.gcloudignore` exclude it). Locally, `docker-compose.yml` mounts it into
  `/docker-entrypoint-initdb.d/`, which runs it **only when the container
  initializes an empty data directory**; Neon was seeded from them by
  `make neon-bootstrap` (docs/deployment-neon.md). So an index added to
  `02_indexes.sql` never reaches an existing database — pair it with a dated
  file in `commands/migrations/` and apply that with `make postgres-query
  FILE=...` locally and `make neon-cli ARGS='-f ...'` on Neon.
  **`books_search_idx` duplicates a Python expression.** It is a GIN index over
  the `to_tsvector(...)` document that `search_document()` in
  `stores/book_store.py` builds, and Postgres matches expression indexes
  *structurally* — so the DDL and the Python must stay character-identical, and
  the expression must compile with no bind parameters in it (a Python `"english"`
  becomes one, and the index silently stops being used: ~5ms back to ~520ms).
  `tests/unit/db/stores/test_lexical_query.py` guards both halves.
- `stores/` — repository pattern; routes/workflows never touch sessions directly.
  `base_store.py` (shared execute helpers), `book_store.py` (primary store: the
  deferred-query API below, plus the module-level `embedding_search_stmt` — a
  pure builder rather than a store method, because only the caller knows the
  label that elides its 1024-float vector from the recorded SQL; it returns a
  `DeferredBookQuery` like every other builder, so `count`/`score_stats`/
  `materialize` are its execute half),
  `chat_run_store.py` (review queue, ordered least-reviewed-first),
  `feedback_store.py` (review upsert).
- **Deferred queries** (`deferred_query.py`). Retrieval nodes do not fetch rows:
  `BookStore.title_query()` / `author_query()` / `lexical_query()` /
  `numeric_traits_query()` and the module-level `embedding_search_stmt()` build a
  statement, `count()` runs only a `COUNT`
  over it, and the statement itself rides downstream on the node's output.
  The split is two questions: **building from a dimension and executing live on
  the store** (they need the model and the session.
  `numeric_traits_query()` applies `metadata_predicates` to the whole catalog,
  which is what lets bounds *be* a search; since 2026-08-24 that is the only
  reading of a bound there is, and `filter_query()` — which ANDed the same
  predicates onto an upstream query for the deleted `Filter_Retrieval` node — is
  gone with it. It is also the one builder that emits no `score` column, so its
  rows fall back to ranking by rating.
  `lexical_query()` is the text one: a full-text match over title + shelf label
  + blurb, ANDed with exact set membership on `books.genre`. It emits a
  `ts_rank` score only when there are keywords, so a shelf-only search falls back
  to rating the same way);
  **everything derivable from
  an already-built query lives on `DeferredBookQuery` itself** — `count_stmt()`,
  `materialize_stmt()`, and `DeferredBookQuery.compose()`, which folds several
  queries into one `WITH` clause (`"or"` pools, `"and"` intersects, both deduped
  by isbn13 in SQL). `materialize()` is the single place rows are fetched — at
  the end of the plan (the UI's sample cards are a small `materialize()` call
  too, streamed and dropped — see `BookWorkflow.fetch_books`). A
  `DeferredBookQuery` selects isbn13 (plus an optional `score`) and carries
  **no LIMIT and no ORDER BY**; that is what makes two of them composable, so
  don't add either when building one.
  **One documented exception** (2026-08-24): `embedding_search_stmt` keeps its
  ORDER BY and LIMIT, because a vector search does not select a subset — it
  orders the whole table and truncates, so the cap *is* the pool.
  `score_stats()` is its counting call, since `count()` on it only ever reports
  the LIMIT. What that costs depends on `op`, and the two halves are not alike:
  **`compose(op="and")` is safe** — the one `score` is carried through, so
  `Combine_Intersect` bounds the pool *with cosine order intact*; the LIMIT is
  still applied first, so the count means "of the 250 nearest, N also match"
  rather than "N in the catalog", which is the caller's to phrase.
  **`compose(op="or")` is lossy and nothing stops you** — the LIMIT applies
  before the union, changing which books qualify, and `score` is dropped after
  (a union contains rows the pool never matched, so there is nothing to carry).
  A tracked `capped` attribute and a guard were tried and removed the same day;
  nothing registered pools a query, since `Combine_Union` does not exist. See
  docs/design/execution-pipeline-v1.md.
- `commands/` — ad-hoc queries (`chat_run_eval.sql`, `example.sql`) and the
  dated `migrations/`, run with `make postgres-query FILE=...`. Like `init/`,
  excluded from the image.

## Tables

| Table | Purpose |
|---|---|
| `books` | Book catalog + pgvector embeddings |
| `chat_runs` | One row per chat turn: user/assistant messages, planner/tasks/writer JSONB (one envelope per layer — `writer` is the reply stage, and the only stored copy of the prose), promoted stats (duration, tokens). PK `chat_id` |
| `feedback` | One review per (chat_id, session_id), upserted whole. FK `chat_id` → `chat_runs`, CASCADE |
| `test_runs` | Eval bookkeeping: chat_id FK → `chat_runs` (CASCADE — deleting chat_runs takes test_runs with it) + suite name + case id |

## Local dev

```bash
make postgres-start     # Docker Compose PostgreSQL
make postgres-restore   # load data/backup.sql
make postgres-cli       # psql shell
make postgres-stop
```

Neon (managed Postgres, the deployed database) — `neon auth` and `neon link`
once per machine, see docs/deployment-neon.md:

```bash
make dev-neon           # make dev with config/.env.neon's POSTGRES_* over config/.env
make neon-cli           # psql shell on Neon
make neon-bootstrap     # seed an EMPTY Neon database from db/init + data/backup/books.sql
```
