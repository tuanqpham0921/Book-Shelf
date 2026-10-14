# 009: no user auth in V1

**Status:** accepted · 2026-09-24

## Context

BookShelf is a public demo with no accounts. Anyone can mint a session id, and every turn spends real OpenAI money. The review routes (`GET /chat_runs`, `GET /feedback`, `PUT /feedback/review`) read and write every recorded turn and had no credential.

## Decision

No user authentication in V1. Instead:

1. **The review routes are not served in production.** Review runs locally against the production database (`make dev-neon`). Session ownership can't protect them: anyone can get a session id, and the reviewer is by design not the run's session.
2. **Firebase App Check guards every route but the health checks.** It proves a request came from the site, not who sent it: a token copied out of devtools replays with curl until it expires, an hour by default. It stops scripts that never load the page.
3. **Spend is capped instead of identity checked:**
   - a token budget per session (200,000), in every environment;
   - a site-wide daily cap, read from the `sessions` table (a made-up session id starts with a full budget);
   - a per-IP message limit, in memory per instance;
   - a hard monthly cap on the OpenAI account, and concurrency × instances as a throughput ceiling.
4. **Chat feedback stays public,** because it can only rate a run recorded under the caller's own session.

## Consequences

- `/review` on the live site fails to load.
- The per-IP limit is per instance, so the real ceiling is up to three times the setting.
- A session can go one turn into the red: the debit lands at the end of the turn.
- **A public review page needs real auth** (Firebase Auth). A token in a `VITE_*` variable is baked into the bundle in plain text. An admin token gate (`APP_ADMIN_TOKEN`, checked with `secrets.compare_digest` at router level) is enough for a private one.
