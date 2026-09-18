# Database strategy — Neon instead of Cloud SQL

> **Companion to [deployment.md](deployment.md)**, which is written for Cloud SQL.
> This file replaces its **Stage 3** entirely and adjusts a few flags in Stages 2,
> 4 and 6. **Stage 1 is unaffected** — the container work is correct either way.
>
> **Status: the database is live** (Steps 1–6, done 2026-09-18). The driver
> claims are checked against the installed SQLAlchemy 2.0.43 and asyncpg 0.29.0;
> the Neon claims against Neon CLI 5.0.0 and the project itself.

---

## Why

### The cost

Cloud SQL has no free tier and cannot scale to zero. The smallest instance that
runs this demo (`db-g1-small`) costs roughly **$28/month to sit idle**, which for
a portfolio demo that gets opened a few times a week is the entire bill.

Neon is managed Postgres with a free tier and **autosuspend** — the compute stops
when nobody is connected, so an idle week costs nothing. The database is **84 MB**
(measured, see below), comfortably inside the free tier's storage.

| Table | Size |
|---|---|
| `books` | 76 MB |
| `chat_runs` | 104 kB |
| `feedback` | 24 kB |
| `test_runs` | 16 kB |
| **total** | **84 MB** |

### Why not SQLite in the container

This was the obvious cheaper idea and it does not survive contact with the query
layer. **Four of the six registered nodes are built on a Postgres extension:**

| Node | Depends on | SQLite equivalent |
|---|---|---|
| `Retrieve_by_Title` | `similarity()` — pg_trgm | **none** |
| `Retrieve_by_Author` | `word_similarity()` — pg_trgm | **none** |
| `Retrieve_by_Lexical_Traits` | `to_tsvector` + GIN | FTS5 — different API |
| `Analyze_Similar_Books` | pgvector `cosine_distance` + ivfflat | sqlite-vec, or numpy |
| `Retrieve_by_Numeric_Traits` | plain predicates | ✅ portable |
| `Combine_Intersect` | CTE union/intersect | ✅ portable |

Two of those have decent answers — vector search over 5,197 × 1024 floats is
21 MB in memory and a brute-force matvec would be *more* accurate than the
current `lists=100` ivfflat index, and FTS5 is a real full-text engine.

**Trigram has no answer.** SQLite has no `similarity()`. The options are a Python
UDF (runs per row, through the interpreter, can never use an index) or moving
fuzzy matching out of SQL into `rapidfuzz`. Both break `DeferredBookQuery`
composition: once the similar-books pool is a Python list instead of a subquery,
`Combine_Intersect` cannot `compose()` against it, and "books like Dune under 300
pages" stops keeping cosine order — which `db/stores/deferred_query.py` documents
as the specific payoff of the current design. Three test files also assert
compiled SQL, and `tests/unit/db/stores/test_lexical_query.py` diffs SQLAlchemy's
output against the DDL in `02_indexes.sql`.

So it is not a driver swap; it is a rewrite of `book_store.py`,
`deferred_query.py`, the models, the schema and their tests.

### Why not move `chat_runs` to a bucket

Also considered, also rejected — on arithmetic. Those tables are **144 kB of an
84 MB database**, so moving them saves nothing on the bill, while
`ChatRunStore.get_all`'s "least-reviewed first" ordering (an outer join plus a
group-by) and the `test_runs ⋈ chat_runs` join behind `make suite-reports` both
become Python loops over downloaded objects. CLAUDE.md calls that second one the
project's golden-test mechanism.

The half that is cheap to move is the half that costs nothing to keep. The half
that costs money is the half that cannot move.

### What Neon keeps

pgvector, pg_trgm, full-text search, JSONB, and every line of the query layer.
**No application code changes** beyond the two connection fixes below — which are
small, and which you want regardless.

---

## Where this slots into the runbook

| deployment.md stage | Status under Neon |
|---|---|
| **Stage 1** — container | ✅ Unchanged, already committed |
| **Stage 2** — Cloud Run | Small edits: drop one API, add real env vars, add the probe |
| **Stage 3** — Cloud SQL | ❌ **Replaced by this document** |
| **Stage 4** — security | One line removed (`roles/cloudsql.client`), one secret renamed |
| **Stage 5** — go public | Unchanged, plus a note on autosuspend in 5.3 |
| **Stage 6** — docs | The Infrastructure claims change target |

### Do this *before* Cloud Run, not after

Your original order put the database third because **Cloud SQL forced it there** —
it needed a GCP project, an enabled API and a socket mount, none of which exist
until Cloud Run does. Neon needs none of that. It is set up entirely from your
laptop.

Running it first buys three things:

- The **first Cloud Run revision is a working one**, with real credentials instead
  of placeholders. No "deploy broken, then reconnect" step.
- The `/ready` **startup probe can be on from the first deploy**, so a
  misconfigured revision never goes live.
- Cloud Run reaches Neon over ordinary TCP+TLS — **the same path your laptop
  uses**. If `make neon-cli` works locally, the deployed service will connect.
  The Cloud SQL socket path had no local equivalent to test against.

The safety property is unchanged: Cloud Run still deploys
`--no-allow-unauthenticated`, and only goes public in Stage 5.

---

## Steps 1–6 — done 2026-09-18

Neon project **`book-shelf`** (`dry-frog-27239435`), branch **`production`**,
database `neondb`, role `neondb_owner` — in **`aws-us-east-2` (Ohio), on
Postgres 18**. Two of those differ from what this section used to plan:

- **There is no GCP region.** Neon creates projects in AWS regions (plus one
  Azure), so `us-central1` was never on offer. Ohio is the nearest to Cloud
  Run's `us-central1` (Iowa) — roughly 10–15 ms each way, for a few round trips
  per chat turn beside LLM calls that take seconds. The traffic now leaves
  Google's network; see Risks.
- **Postgres 18, not 16.** The local container is `pgvector/pgvector:pg16`. A
  data-only dump from 16 loads into 18, and nothing in the schema is
  version-specific. The one visible skew is the local psql 16 talking to an 18
  server, which warns on `\d`-style meta-commands — so the checkpoint below
  uses plain SQL.

### 1. Connection settings

`config/settings/sqlalchemy.py` gained **`SSL_MODE`** (default `prefer`, so the
compose container, every existing `.env` and the CI env block connect
unchanged) and now percent-encodes the credentials, because Neon generates the
password. The URL carries **`ssl=`, not `sslmode=`**: SQLAlchemy's asyncpg
dialect forwards every query parameter to `asyncpg.connect()` as a keyword
argument, and that has `ssl` but no `sslmode` — so Neon's `?sslmode=require`
pasted as-is raises `TypeError: connect() got an unexpected keyword argument
'sslmode'` at connect time. `tests/unit/config/test_settings.py` guards the
spelling and the escaping. The `/cloudsql/` socket branch is gone, with its
tests.

**Keep `pool_pre_ping=True`** in `db/async_engine.py`. It drops a connection
that died while Neon suspended the compute, which is what makes autosuspend
invisible rather than a 500 on the first chat after a quiet hour.

### 2. Link, and where the credentials live

```bash
cd backend
neon auth    # once per machine — browser sign-in; the CLI keeps the token
neon link --project-id dry-frog-27239435 --branch production --no-env-pull --no-config -y
```

`neon link` writes the IDs to `backend/.neon` (and added that file to
`.gitignore` itself). **`--no-env-pull` matters**: a pull writes `DATABASE_URL`
into `config/.env`, which the app never reads — it reads the `POSTGRES_*`
fields. Instead the **direct** connection string (`neon connection-string`'s
default — not the `-pooler` host) is split into **`config/.env.neon`**, which
holds only those fields:

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

`config/.env` stays pointed at the local container. `make dev-neon` sources
`.env.neon` over it — process env beats the env file in pydantic-settings — so
switching databases is a target, not a file copy. `config/.env.neon` is covered
by the existing `config/.env*` gitignore rule and by both `.dockerignore` and
`.gcloudignore`.

**Direct, although Neon's own guidance says pooled for web apps.** The
`-pooler` host is PgBouncer in transaction mode. SQLAlchemy already pools
(`db/async_engine.py`), and asyncpg's prepared-statement cache is the classic
casualty of a second pool in front of it. One long-lived Cloud Run service
holding at most 36 connections (Pool sizing) gives PgBouncer nothing to solve.

### 3. Makefile targets

| Target | Does |
|---|---|
| `make neon-cli` | psql shell on Neon; `ARGS='-c "…"'` or `ARGS='-f file.sql'` for one command or file |
| `make postgres-dump-books` | the local container's `books`, data only, COPY format → `data/backup/books.sql` |
| `make neon-bootstrap` | extensions → tables → books → indexes, each file with `ON_ERROR_STOP=1` |
| `make dev-neon` | `make dev` with `config/.env.neon` loaded over `config/.env` (same port — stop `make dev` first) |

The Neon targets go through **`neon psql`**, which finds the project in `.neon`
and the password through your Neon login. So there is no operator credential
in `config/.env` (the old plan's `NEON_URL`), and a mistyped host cannot point
a write at the local container. `ON_ERROR_STOP=1` matters: without it psql
reports an error and keeps going, so a failed `CREATE EXTENSION` would surface
as a confusing error at the end of the books load.

### 4. The books dump

`data/backup/` is gitignored — the old `*backup.sql` rule did not match
`books.sql`. The dump is **67 MB**. Keep it: regenerating 5,197 embeddings
costs real OpenAI spend and `data/books.csv` has no vectors, so the local
container, this file and Neon are the only three copies.

### 5. Bootstrap order

`make neon-bootstrap` took 1m23s. The order is load-bearing:

1. **`00_extensions.sql`** — `vector` and `pg_trgm` (Neon allows both without
   superuser). The books load fails without the `vector` type.
2. **`01_tables.sql`**
3. **`books.sql`**
4. **`02_indexes.sql`, last.** `books_embedding_idx` is ivfflat, which builds
   its centroids from the rows present when the index is created. Built on an
   empty table, similarity recall degrades *silently* — answers still come
   back, just worse ones.

**No migration runner.** Every file in `db/commands/migrations/` is already
folded into `db/init/`, so a fresh database gets the current schema from
`00/01/02`. A schema change lands in `db/init/0*.sql` **and** a dated
migration, and the migration reaches Neon with
`make neon-cli ARGS='-f db/commands/migrations/<file>.sql'` — ideally tried on
a Neon branch first (see Next steps).

### 6. ✅ Checkpoint — passed 2026-09-18

```bash
make neon-cli ARGS='-c "SELECT extname, extversion FROM pg_extension;"'   # vector 0.8.6, pg_trgm 1.6
make neon-cli ARGS='-c "SELECT count(*), count(embedding) FROM books;"'   # 5197 | 5197
make neon-cli ARGS='-c "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema();"'  # 8
make dev-neon              # then, from another shell:
curl localhost:8000/ready  # 200
```

Eight indexes is the four from `02_indexes.sql` plus the four primary keys.
One real turn — "books like Dune under 300 pages" — ran all four goals against
Neon (Dune → 2,429 short books → 250 similar → 49 after the intersect) and
streamed cards and prose.

### Next steps

- **Branch before a migration.** `neon branches create --name mig-<topic>`
  is an instant copy-on-write clone of production with all 5,197 books; apply
  the dated migration there, point `config/.env.neon` at its host, exercise it
  with `make dev-neon`, then apply it to `production`. It is the first time a
  schema change can be tested against real data before it lands.
- **Stage 2 next.** Cloud Run can deploy with real credentials and the
  `/ready` startup probe from its first revision (below).
- **Neon's other services** — Object Storage, Functions, the AI Gateway —
  are all available in `aws-us-east-2`, but nothing in the app is looking for
  a home: there are no uploads, the API already runs on Cloud Run, and
  `clients/` owns the OpenAI calls. Revisit only if one of those changes.

---

## What changes in deployment.md's other stages

### Stage 2 — Cloud Run

**2.1** — drop `sqladmin.googleapis.com` from the `gcloud services enable` list.
There is no Cloud SQL instance to administer.

**2.2** — the deploy now carries real credentials and a startup probe. Set the
values first so no secret lands in shell history:

```bash
NEON_HOST=ep-<name>-<id>.us-east-2.aws.neon.tech   # POSTGRES_HOST in config/.env.neon
NEON_USER=neondb_owner
NEON_DB=neondb
read -rs -p "Neon password: "   NEON_PW;    echo
read -rs -p "OpenAI API key: "  OPENAI_KEY; echo
```

```bash
gcloud run deploy book-shelf-api \
  --source=backend/ --region=$REGION --no-allow-unauthenticated \
  --cpu=1 --memory=1Gi --cpu-boost --timeout=300 \
  --min-instances=0 --max-instances=3 --concurrency=5 \
  --startup-probe=httpGet.path=/ready,initialDelaySeconds=5,timeoutSeconds=5,periodSeconds=5,failureThreshold=6 \
  --set-env-vars="^@^APP_NAME=book-recommender-backend@APP_ENVIRONMENT=production@APP_ALLOW_ORIGINS=http://localhost:3000@POSTGRES_HOST=$NEON_HOST@POSTGRES_PORT=5432@POSTGRES_DB=$NEON_DB@POSTGRES_USER=$NEON_USER@POSTGRES_PASSWORD=$NEON_PW@POSTGRES_SSL_MODE=require@POSTGRES_MIN_CONNECTIONS=2@POSTGRES_MAX_CONNECTIONS=12@OPENAI_API_KEY=$OPENAI_KEY@OPENAI_BASE_MODEL=gpt-4.1-mini@OPENAI_TOKENIZER_ENCODING=o200k_base@OPENAI_EMBEDDING_MODEL=text-embedding-3-large@OPENAI_EMBEDDING_DIMENSIONS=1024@OPENAI_MAX_CONCURRENCY=10"
```

- **`^@^` is still load-bearing** — it changes gcloud's list delimiter from `,` to
  `@`, and `APP_ALLOW_ORIGINS` gains a comma in Stage 5.
- **`POSTGRES_SSL_MODE=require` is not optional.** Neon refuses plaintext. The
  default `prefer` would negotiate TLS anyway, but it *silently falls back* to
  plaintext if TLS fails, and you want an error instead.
- The two secrets are plain env vars here, readable by anyone with console access.
  Stage 4.5 moves them to Secret Manager; that section is self-contained if you
  want it sooner.

**The `/ready` startup probe earns its place.** Cloud Run's default check is
TCP-on-`$PORT`, and since `common/context.py:44-48` has `ping_services()`
commented out, a container with a wrong host binds the port and goes live serving
500s on every chat. `/ready` runs a real `SELECT 1` (`health.py:20-46` already
returns 503 on failure), so a bad host, wrong password or missing `ssl=require`
means the revision **never goes live and the previous one keeps serving**.

Do **not** re-enable `ping_services()` instead — it also calls
`OpenAIClient.ping()`, a billed API call on every cold start. Nothing else calls
it; delete it with the dead comment.

No liveness probe: a transient blip would kill healthy containers mid-stream, and
Neon resuming from autosuspend looks exactly like one.

### Stage 4 — security

**4.5** — remove the `roles/cloudsql.client` binding; the database is reached over
ordinary TLS, so the service account needs nothing but secret access. That is a
feature: it becomes the least-privileged identity in the project. The secret is
still called `postgres-password`; it just holds `$NEON_PW`.

**4.6** — the Neon host, user and database are plain `--set-env-vars` values and
belong in the `make deploy` recipe; the password and API key come from
`--set-secrets` by then, so the target holds no credential and is safe to commit.

**Stage 4 checkpoint** — read back with
`make neon-cli ARGS='-c "SELECT chat_id, user_message FROM chat_runs ORDER BY created_at DESC LIMIT 5;"'`.

### Stage 5 — go public

**5.3** — `--min-instances=1` now buys two things, not one. A warm instance also
holds a connection open, which stops Neon autosuspending, so the first chat after
a quiet hour skips both the container cold start *and* the database resume. The
trade is that it also stops your free-tier compute hours from idling — watch usage
for a week before leaving it on.

### Stage 6 — docs

Done with the database: `CLAUDE.md` and `README.md` name Neon as the database,
and `backend/db/README.md` covers both targets (the local container via
`config/.env`, Neon via `config/.env.neon` and `make dev-neon`). The Cloud Run
lines follow once Stage 2 is real.

---

## Pool sizing

The binding constraint is easy to miss. `get_sqlalchemy_session`
(`app/api/dependencies.py:42-53`) is a **`yield` dependency**, so its connection
is held for the *entire SSE stream*, not per query — and once Stage 4 uncomments
the recorder, `record_chat_run` opens a **second, independent** session while the
first is still open. Peak is **2 connections per in-flight turn**.

| Knob | Value | Why |
|---|---|---|
| `--concurrency` | 5 | 5 turns × 2 conns = 10 |
| `--max-instances` | 3 | ~15 concurrent turns; under the 500 RPM tier in `docs/backlog.md:52-58` |
| `POSTGRES_MIN_CONNECTIONS` | 2 | `pool_size` |
| `POSTGRES_MAX_CONNECTIONS` | 12 | pool 2 + overflow 10 (`db/async_engine.py:32-34`) |
| Worst case | 36 | 3 × 12 |

The shipped defaults (`.env.example:18-19`, MIN=5/MAX=20) are **per instance** — at
3 instances that is 60. Both are env-driven, so this is config, not code. Check
the real ceiling with `make neon-cli ARGS='-c "SHOW max_connections;"'`; Neon sets
it from compute size — **901** on this project's 0.25–2 CU autoscaling range, so
36 is nowhere near it.

---

## Deferred, with reasons

- **`lists = 100` is wrong for 5,197 rows.** pgvector's guidance is `rows/1000` ≈ 5.
  At 100 each list holds ~52 rows and the default `ivfflat.probes = 1` scans one —
  recalling ~1% of the table per query. At this size an exact scan is single-digit
  milliseconds anyway. **Keep 100 for parity with local** (changing it changes eval
  results) and treat it as a recall question, not a deploy action.
- **`verify-full` instead of `require`.** `require` encrypts but does not verify
  the certificate, so it does not stop an active man-in-the-middle. `verify-full`
  does, Neon's certificates are from a public CA, and `python:3.12-slim` ships the
  CA bundle to validate against — so it is a one-word change to
  `POSTGRES_SSL_MODE`. Left until after the deploy works, because a certificate
  problem and a connection problem look identical from outside and you do not want
  to debug both at once.
- **pandas is never imported at runtime** (verified by grep across `app/ common/
  db/ clients/ config/ airglider/`). It pulls ~100MB with numpy for evals and
  notebooks only. Moving it to the dev group is correct but churns `poetry.lock` —
  do it after the image is proven.

---

## Risks

- **The free tier is a real ceiling.** Neon's free plan caps storage (~0.5 GB —
  you are at 84 MB) and monthly compute hours. Check the current limits when you
  sign up rather than trusting this line, and watch usage for the first week. A
  paid tier is still far below Cloud SQL, so the failure mode is a small bill, not
  an outage — set a billing alert anyway.
- **Autosuspend adds latency to the first query after idle**, on top of the Cloud
  Run cold start you already accepted. `pool_pre_ping=True` makes it *correct*; it
  does not make it *fast*. Stage 5.3 is the lever.
- **Neon is a third party, on another cloud.** It runs in AWS `us-east-2`, so
  Cloud Run reaches it over the public internet: another account, another status
  page, and another thing that can change its free tier. Cloud Run bills internet
  egress, but a turn moves kilobytes — no query returns the `embedding` column.
  Nothing is locked in: it is stock Postgres, so moving to Cloud SQL later is
  `pg_dump` plus five env vars.
- **Local is 16, Neon is 18.** Harmless today; if a query ever behaves
  differently between the two, suspect the version before the code.
