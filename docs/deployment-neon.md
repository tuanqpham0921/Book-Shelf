# The database: Neon

**Updated:** 2026-10-08 · Companion to [deployment.md](deployment.md).

Neon project **`book-shelf`** (`dry-frog-27239435`), branch **`production`**, database
`neondb`, role `neondb_owner`, in **`aws-us-east-2` (Ohio)**, on **Postgres 18**. Local
development uses the Docker Compose container (`pgvector/pgvector:pg16`) through
`config/.env`.

## Why Neon

- **Cost.** Cloud SQL has no free tier and cannot scale to zero; its smallest usable
  instance costs about $28/month idle. Neon has a free tier and **autosuspend**, and the
  database (~84 MB, almost all of it `books`) fits inside it.
- **Not SQLite.** Four of the book nodes depend on Postgres extensions: trigram
  `similarity()` for title and author (SQLite has no equivalent), `to_tsvector` + GIN for
  lexical search, and pgvector for similarity. Moving trigram matching into Python would
  break `DeferredBookQuery` composition — the similarity pool would become a list
  `Combine_Intersect` cannot compose against.
- **Not a bucket for `chat_runs`.** Those tables are kilobytes, so moving them saves
  nothing, while the review queue's ordering and the `test_runs ⋈ chat_runs` join behind
  the golden test would become Python loops.

Neon keeps pgvector, pg_trgm, full-text search, JSONB and every line of the query layer.
It is stock Postgres: moving to Cloud SQL later is `pg_dump` plus five env vars.

## Connecting

**Credentials.** The direct connection string is split into git-ignored
**`config/.env.neon`**, which holds only the `POSTGRES_*` fields:

```bash
POSTGRES_HOST=ep-<name>-<id>.us-east-2.aws.neon.tech
POSTGRES_PORT=5432
POSTGRES_DB=neondb
POSTGRES_USER=neondb_owner
POSTGRES_PASSWORD='npg_…'
POSTGRES_SSL_MODE=require
POSTGRES_MIN_CONNECTIONS=2
POSTGRES_MAX_CONNECTIONS=12
```

`config/.env` stays pointed at the local container. `make dev-neon` loads `.env.neon`
over it (process env beats the env file in pydantic-settings), so switching databases is
a target, not a file copy. The same file feeds `make deploy`. It is covered by the
`config/.env*` gitignore rule and by both `.dockerignore` and `.gcloudignore`.

**Linking the CLI** (once per machine):

```bash
cd backend
neon auth
neon link --project-id dry-frog-27239435 --branch production --no-env-pull --no-config -y
```

`--no-env-pull` matters: a pull writes `DATABASE_URL` into `config/.env`, which the app
never reads.

**Connection settings** (`config/settings/sqlalchemy.py`, `db/async_engine.py`):

- **`ssl=`, not `sslmode=`.** SQLAlchemy's asyncpg dialect forwards URL parameters to
  `asyncpg.connect()`, which has `ssl` but no `sslmode`; Neon's own
  `?sslmode=require` raises at connect time. Credentials are percent-encoded, because
  Neon generates the password. `tests/unit/config/test_settings.py` guards both.
- **`POSTGRES_SSL_MODE=require` in production.** The default `prefer` silently falls back
  to plaintext if TLS fails; you want an error instead.
- **The direct host, not `-pooler`.** The `-pooler` host is PgBouncer in transaction
  mode: SQLAlchemy already pools, asyncpg's prepared-statement cache is the classic
  casualty of a second pool, and PgBouncer rejects the `statement_timeout` startup
  parameter the engine sets.
- **`pool_pre_ping=True`** drops a connection that died while Neon suspended the
  compute, which is what makes autosuspend invisible rather than a 500 on the first chat
  after a quiet hour.
- **Timeouts, layered:** `AppConfig.DATABASE_TIMEOUT` drives `statement_timeout` (the
  server cancels; the connection stays usable), asyncpg's `command_timeout` just above
  it, and `pool_timeout` plus the connect `timeout` for the waits Postgres cannot see.

## Make targets

| Target | Does |
|---|---|
| `make neon-cli` | psql on Neon; `ARGS='-c "…"'` or `ARGS='-f file.sql'` for one command or file |
| `make dev-neon` / `make local-prod-neon` | `make dev` / `make local-prod` against Neon (same port — stop the local one first) |
| `make postgres-dump-books` | the local container's `books`, data only, COPY format → `data/backup/books.sql` |
| `make neon-bootstrap` | extensions → tables → books → indexes, each with `ON_ERROR_STOP=1` |

The Neon targets go through **`neon psql`**, which finds the project in `backend/.neon`
and authenticates through your Neon login, so no operator credential lives in
`config/.env`. `ON_ERROR_STOP=1` stops a failed `CREATE EXTENSION` from surfacing later
as a confusing error in the books load.

## Bootstrapping a fresh database

`make neon-bootstrap` (about 1.5 minutes). The order is load-bearing:

1. **`db/init/00_extensions.sql`** — `vector` and `pg_trgm`. The books load fails
   without the `vector` type.
2. **`db/init/01_tables.sql`**
3. **`data/backup/books.sql`** — 67 MB, git-ignored. Keep it: it is one of only three
   copies of the embeddings.
4. **`db/init/02_indexes.sql`, last.** `books_embedding_idx` is ivfflat, which builds
   its centroids from the rows present at creation. Built on an empty table, similarity
   recall degrades *silently* — answers still come back, just worse ones.

**Check:**

```bash
make neon-cli ARGS='-c "SELECT extname, extversion FROM pg_extension;"'   # vector, pg_trgm
make neon-cli ARGS='-c "SELECT count(*), count(embedding) FROM books;"'   # 5197 | 5197
make dev-neon   # then: curl localhost:8000/ready → 200
```

Use plain SQL rather than `\d`-style meta-commands: local psql 16 warns against an 18
server.

## Schema changes

There is no migration runner. A schema change lands in `db/init/0*.sql` **and** a dated
file in `db/commands/migrations/`, so a fresh database gets the current schema from
`00/01/02` alone. Apply the migration with
`make neon-cli ARGS='-f db/commands/migrations/<file>.sql'`.

**Try it on a branch first.** `neon branches create --name mig-<topic>` is an instant
copy-on-write clone of production with all the books. Apply the migration there, point
`config/.env.neon` at the branch host, exercise it with `make dev-neon`, then apply it to
`production`.

## Pool sizing

Sessions are opened per unit of work (`ctx.store(...)`) and closed on exit, so a
connection is held only around a round trip, not for a whole SSE stream.

| Knob | Value | Why |
|---|---|---|
| `--concurrency` × `--max-instances` | 5 × 3 | ~15 concurrent turns |
| `POSTGRES_MIN_CONNECTIONS` | 2 | `pool_size` per instance |
| `POSTGRES_MAX_CONNECTIONS` | 12 | pool 2 + overflow 10 per instance |
| Worst case | 36 | 3 instances × 12 |

Neon sets `max_connections` from compute size — 901 on this project's 0.25–2 CU range — so
36 is nowhere near it. The defaults in `config/.env.example` (5/20) are per instance and
too high for three instances.

## Autosuspend

Neon suspends after 5 minutes with no active queries and closes idle connections when it
does; an open pool does not keep it awake. The first chat after a quiet spell pays a
resume of a few hundred milliseconds, which `pool_pre_ping` absorbs by reconnecting.
Cloud Run `--min-instances=1` warms the container, not the database. Keeping Neon awake
means turning off scale-to-zero, a paid-plan setting — not worth it for a demo whose LLM
calls take seconds. No liveness probe either: a resume looks exactly like a transient
blip, and a probe would kill healthy containers mid-stream.

## Deferred

- **`lists = 100` is wrong for 5,197 rows.** pgvector's guidance is `rows/1000` ≈ 5; at
  100 with `probes = 1`, a query scans ~1% of the table. An exact scan would be
  single-digit milliseconds at this size. Kept at 100 for parity with local, since
  changing it changes eval results — a recall question, not a deploy action.
- **`verify-full` instead of `require`.** `require` encrypts but does not verify the
  certificate, so it doesn't stop an active man-in-the-middle. Neon's certificates are
  from a public CA and the image ships the CA bundle, so it is a one-word change to
  `POSTGRES_SSL_MODE`.

## Risks

- **The free tier is a ceiling** on storage and monthly compute hours. Watch usage; the
  failure mode is a small bill, not an outage. Keep a billing alert.
- **Another cloud.** Neon runs on AWS `us-east-2` and Cloud Run in GCP `us-east5`, so
  traffic crosses the public internet. A turn moves kilobytes — no query returns the
  `embedding` column.
- **Local is 16, Neon is 18.** Harmless so far; if a query behaves differently between
  the two, suspect the version before the code.
