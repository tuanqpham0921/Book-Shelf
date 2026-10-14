# 007: Neon for the production database

**Status:** accepted

## Context

Production needed a Postgres that a demo with little traffic can afford. The database is about 84 MB, almost all of it the `books` table.

## Decision

**Neon** (managed Postgres 18, `aws-us-east-2`), over two cheaper-looking alternatives:

- **Not Cloud SQL.** It has no free tier and can't scale to zero; its smallest usable instance costs about $28 a month idle. Neon has a free tier and autosuspend, and the database fits inside it.
- **Not SQLite.** Four book nodes depend on Postgres extensions: trigram `similarity()` for titles and authors, `to_tsvector` with a GIN index for lexical search, and pgvector for similarity. Moving trigram matching into Python would also break query composition ([005](005-counts-first-retrieval.md)).
- **Not a storage bucket for `chat_runs`.** Those tables are kilobytes, so moving them saves nothing, while the review queue's ordering and the join behind the golden test would become Python loops.

## Consequences

- It is stock Postgres, so moving to Cloud SQL later is `pg_dump` plus five env vars.
- The free tier is a ceiling on storage and compute hours. The failure mode is a small bill, not an outage.
- Neon runs on AWS and Cloud Run on GCP, so traffic crosses the public internet. A turn moves kilobytes, since no query returns the embedding column.
- Autosuspend means the first chat after a quiet spell pays a resume of a few hundred milliseconds.
- Local development runs Postgres 16, production 18. If a query behaves differently between them, suspect the version first.
