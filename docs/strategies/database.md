# Database strategy

BookShelf's production database is Neon project `book-shelf` (branch `production`, database `neondb`) on Postgres 18 in `aws-us-east-2`. Local development uses the Docker Compose container instead. Why Neon: [decision 007](../decisions/007-neon.md). The commands: [backend/db/](../../backend/db/README.md).

## Connection choices

- **`ssl=`, not `sslmode=`.** SQLAlchemy's asyncpg dialect hands URL parameters to `asyncpg.connect()`, which has no `sslmode`, so Neon's own connection string raises at connect time. The password is percent-encoded, because Neon generates it. `tests/unit/config/test_settings.py` guards both.
- **`POSTGRES_SSL_MODE=require` in production.** The default `prefer` falls back to plaintext if TLS fails; production should error instead.
- **The direct host, not `-pooler`.** The pooler is PgBouncer in transaction mode. SQLAlchemy already pools, asyncpg's prepared-statement cache breaks under a second pool, and PgBouncer rejects the `statement_timeout` startup parameter the engine sets.
- **`pool_pre_ping`** drops a connection that died while Neon suspended, so autosuspend shows up as a short delay, not a 500 on the first chat after a quiet hour.
- **No liveness probe.** A Neon resume looks exactly like a transient blip, and a probe would kill healthy containers mid-stream.
- **Neon's own login, not a stored credential.** The Neon make targets go through `neon psql`, so no operator credential lives in `config/.env`.

## Pool sizing

A connection is held only around a round trip, not for a whole SSE stream ([decision 008](../decisions/008-session-per-unit-of-work.md)).

| Setting | Value | Why |
|---|---|---|
| concurrency × instances | 5 × 3 | about 15 concurrent turns |
| `POSTGRES_MIN_CONNECTIONS` | 2 | the pool per instance |
| `POSTGRES_MAX_CONNECTIONS` | 12 | pool plus overflow per instance |
| worst case | 36 | 3 instances × 12, against Neon's 901 |

The defaults in `config/.env.example` (5 and 20) are per instance, and too high for three instances.

## Autosuspend

Neon suspends after 5 minutes without queries and closes idle connections; an open pool doesn't keep it awake. Keeping it awake means turning off scale-to-zero, a paid setting, which isn't worth it when the LLM calls take seconds.

## Schema changes

There is no migration runner. A change lands in `db/init/`, so a fresh database gets the current schema, and the same DDL is applied by hand to each existing database. On Neon, try it first on a branch, an instant copy-on-write clone of production with all the books.

**Bootstrap order is load-bearing:** extensions, tables, the books, then the indexes. The similarity index is ivfflat, which builds its centroids from the rows present when it is created; built on an empty table, recall degrades silently.

## Open

- **`lists = 100` is wrong for 5,197 rows.** pgvector's guidance is rows/1000, about 5. It stays at 100 for parity with local, since changing it changes eval results.
- **`verify-full` instead of `require`.** `require` encrypts but doesn't verify the certificate. Neon's certificates are from a public CA and the image ships the CA bundle, so it is a one-word change.
