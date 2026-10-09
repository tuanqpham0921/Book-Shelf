# Deploying BookShelf

**Updated:** 2026-10-08 · The database half is in [deployment-neon.md](deployment-neon.md).

## 1. Status

**Live.** Anyone can open [tuanqpham0921.web.app](https://tuanqpham0921.web.app) and chat.

| Piece | Value |
|---|---|
| Cloud Run service | `book-shelf-api`, region `us-east5`, project `tuanqpham0921` (number 286869228046) |
| URL | `https://book-shelf-api-imqv7vxzdq-ul.a.run.app` — public (`allUsers` → `roles/run.invoker`) |
| Shape | cpu 1, memory 1Gi, cpu-boost, timeout 300s, min 0 / max 3 instances, concurrency 5 |
| Identity | `book-shelf-api@tuanqpham0921.iam.gserviceaccount.com`, not the compute default (which carries project Editor) |
| Secrets | `POSTGRES_PASSWORD` ← `postgres-password:latest`, `OPENAI_API_KEY` ← `openai-api-key:latest` |
| OpenAI key | Production has its **own key**, separate from the one in `config/.env` that `make dev` and `dev-neon` use. It lives in git-ignored `config/.env.deployment`; `make deploy` pushes it as a new `openai-api-key` version when it differs from `latest` |
| Vector store | `OPENAI_VECTOR_STORE_ID` (the project docs `Retrieve_Project_Info` searches), read from `config/.env.deployment` into `--set-env-vars` — an id, not a secret |
| Startup probe | `GET /ready` (a real `SELECT 1`), 5s delay / 5s period / 6 failures — a revision that can't reach the database never takes traffic |
| Database | Neon — [deployment-neon.md](deployment-neon.md) |
| Frontend | Firebase Hosting, target `book-rec`; `VITE_API_URL` from the committed `frontend/.env.production` |

## 2. Deploying

```bash
make -C backend deploy        # build with Cloud Build, deploy, then deploy-check
make -C backend deploy-check  # curl /ready on the live revision — 200 means image, env, secrets and DB are wired
make -C frontend deploy       # build + publish to Firebase Hosting
```

**The `deploy` recipe in `backend/Makefile` is the whole description of the service.**
Change a setting there, not in the console. There is no `cloudbuild.yaml` and there
shouldn't be: `gcloud run deploy --source` already runs Cloud Build and pushes to
Artifact Registry, so the file would only restate the Dockerfile and the flags.

Details worth knowing:

- The database host, user and pool values come from git-ignored `config/.env.neon` — the
  same file `make dev-neon` reads — so the deployed database and local Neon runs cannot
  drift, and the endpoint stays out of the public repo.
- **`^@^` in `--set-env-vars` is load-bearing.** It switches gcloud's list delimiter from
  `,` to `@`, so the comma inside `APP_ALLOW_ORIGINS` doesn't split it into two malformed
  variables.

**Kill switch:**

```bash
make -C backend deploy-off    # revoke public access (403s); nothing is deleted
make -C backend deploy-on     # restore it without a rebuild, then deploy-check
```

**Rotating the OpenAI key:**

Put the new key in `OPENAI_API_KEY` in `backend/config/.env.deployment`, then:

```bash
make -C backend deploy        # adds the secret version, then deploys; `latest` is resolved when an instance starts
```

The recipe pipes the key with `printf '%s'`, never `echo`: a trailing newline breaks auth
in a way that looks exactly like a wrong credential.

## 3. The image

`backend/Dockerfile`, build context `backend/`:

- **Multi-stage, `python:3.12-slim`;** `poetry install --only main --no-root`. The app runs
  from source with `WORKDIR` on `sys.path`, like `make dev`.
- **An explicit copy list:** `airglider app clients common config db`. A whole-directory
  copy is what carries the prompt `.txt` files; a `**/*.py` pattern would drop them and
  fail on the first request, not at boot.
- **The tiktoken encodings are baked in** (`TIKTOKEN_CACHE_DIR=/app/.tiktoken`), so a cold
  start doesn't download them on a user's first request.
- **`$PORT` is honoured** through `sh -c` with `exec`, so uvicorn is PID 1 and receives
  Cloud Run's SIGTERM. One worker; Cloud Run scales by instance.
- **Non-root, without `chown`.** `/app` stays root-owned and read-only, so a stray write
  fails loudly. The consequence: the image only boots as `APP_ENVIRONMENT=production`,
  because development writes a log file. Local dev is `make dev`.

**Two ignore files, with different matching rules.** `.dockerignore` uses Docker's
matcher (bare `*` plus `!name` negations work); `.gcloudignore` uses gitignore semantics,
so **every line is anchored with a leading `/`**, and it keeps `Dockerfile` because Cloud
Build needs it in the uploaded tarball. Both exclude `config/.env*`, `logs/`, `data/`,
`evals/`, `playground/`, `tests/`, `.venv` and the SQL under `db/`. Without a
`.gcloudignore`, gcloud writes one into the repo for you.

**Testing the image locally:**

```bash
cd backend
docker build -t book-shelf-api .
docker run --rm --network host -e PORT=8080 \
  --env-file config/.env -e APP_ENVIRONMENT=production book-shelf-api
curl localhost:8080/ready
```

## 4. Security and spend

**Standing mitigations:** a hard monthly spend cap on the OpenAI account, and
`--concurrency=5 × --max-instances=3` as a throughput ceiling.

### 4.1 Admin gate — open

The review surface (`GET /chat_runs`, `GET /feedback`, `PUT /feedback/review`) has no
credential and no ownership check. **It is not served in production**: `app/main.py`
registers those routers only outside production, which closes the disclosure. Review
locally with `make dev-neon` against the same database; `/review` on the live site fails
to load.

This stays open only if the review page should ever go public. Session ownership cannot
protect it — `POST /session/new` hands out ids to anyone, and the reviewer is by design
not the run's session — so it needs an admin gate:

- `config/settings/app.py`: `ADMIN_TOKEN: str` (picked up as `APP_ADMIN_TOKEN`).
- `app/api/dependencies.py`: `require_admin`, comparing with `secrets.compare_digest`.
- `app/main.py`: apply it router-level, so routes added later are covered.
- Add `APP_ADMIN_TOKEN` to `config/.env.example` and the CI env block, and
  `X-Admin-Token` to the CORS headers.

A `VITE_*` value is baked into the bundle in plain text, so a token cannot protect a
*public* review page. That needs real auth (Firebase Auth), not a bundled secret.

### 4.2 Recording

`record_chat_run` (`app/orchestration/run_recorder.py`) picks one sink per environment:
production inserts a `chat_runs` row through `ctx.store(ChatRunStore)`, development writes
JSON files under `logs/<chat_id>/`, test writes nothing. Both sinks sit in one `try`:
recording never costs the user their reply. Files are never the production sink, because
Cloud Run's filesystem is in-memory.

### 4.3 CORS

Exact origins from `APP_ALLOW_ORIGINS` (both Firebase hostnames, set by the recipe).
`allow_credentials=True`, so `*` would be rejected by browsers anyway.
`allow_methods` is `GET, POST, PUT, OPTIONS`; `allow_headers` is `Content-Type` and
`X-Firebase-AppCheck` — exactly what `frontend/src/api.js` sends.

### 4.4 Message bounds

Chat messages are capped at 2,000 characters in the chat route (the literal should move
onto `ChatIn` — [backlog.md](backlog.md)). Feedback comments are bounded on the schema:
`AppConfig.FEEDBACK_MAX_COMMENTS` comments of `FEEDBACK_COMMENT_LENGTH` characters.

### 4.5 Secrets and service account

Secrets live in Secret Manager and reach the service through `--set-secrets`, so the
recipe holds no credential and is safe to commit. The dedicated service account needs only
`roles/secretmanager.secretAccessor` on the two secrets — the database is reached over
ordinary TLS, so it needs no database role.

### 4.6 Firebase App Check

Every route but `/health`, `/ping` and `/ready` requires an App Check token in
`X-Firebase-AppCheck`. `require_app_check` (`app/api/dependencies.py`) verifies it with
PyJWT against Firebase's JWKS (RS256, audience `projects/<number>`, issuer
`https://firebaseappcheck.googleapis.com/<number>`). It is enforced exactly when
`APP_FIREBASE_PROJECT_NUMBER` is set, which the recipe does and local dev doesn't. The
frontend mints tokens with the reCAPTCHA Enterprise provider, from the `VITE_FIREBASE_*`
and `VITE_RECAPTCHA_SITE_KEY` values in `.env.production`.

**It is not authentication.** A token copied out of devtools replays with curl until it
expires (an hour by default). It stops scripts that never load the page, not a person who
does.

### 4.7 Spend caps

- **Per session:** `AppConfig.SESSION_TOKEN_BUDGET` (200,000), enforced in every
  environment. A spent session gets an SSE `error` event, and a turn's whole spend is
  debited at the end, so a session can go one turn into the red.
- **Site-wide, per day (production only):** the session id comes from the URL, so a
  made-up one starts with a full budget. `Orchestrator.run` therefore reads
  `read_site_spend` (every session active in the last 24h, summed as budget minus
  remaining) and refuses past `AppConfig.SITE_DAILY_TOKEN_BUDGET` (3,000,000). Derived
  from `sessions`, so there is no second counter.
- **Per IP (production only):** `limit_messages_per_ip` on the chat route —
  `AppConfig.MESSAGES_PER_IP` (30) per hour, keyed on the last `X-Forwarded-For` entry,
  in memory per instance. The real ceiling is up to 3× that.
- **Chat feedback** (`PUT /session/{session_id}/message/{chat_id}/feedback`) is served in
  production. It 404s unless `ChatRunStore.belongs_to` finds the run under that session,
  so a session can rate only runs it paid for, one row each.

## 5. The frontend

`VITE_API_URL` is committed per Vite mode: `frontend/.env.development` (localhost:8000)
for `npm run dev`, `frontend/.env.production` (the Cloud Run URL) for `npm run build`. So
`make deploy` cannot ship the wrong backend, and a fresh clone builds the same bundle. A
git-ignored `.env.local` overrides either.

## 6. Open items and risks

- **§4.1**, if the review page should ever go public.
- **`uuid_8()`'s 32 bits** — a collision loses one `chat_runs` record, not a reply
  ([backlog.md](backlog.md)).
- **`min-instances=1`** would remove the 5–8s first-chat cold start for about $7/month.
  It warms the container, not the database (see the Neon runbook).
- **pandas is never imported at runtime** but ships ~100MB with numpy. Moving it to the
  dev group is correct; it churns `poetry.lock`.
- **The books data has three copies:** the local container, the 67MB dump in
  `data/backup/` (git-ignored), and Neon. Re-embedding 5,197 books costs real OpenAI
  spend, and `data/books.csv` has no vectors. Keep the dump.
- **GitHub Actions CD** is not set up; `.github/workflows/ci.yml` already has the env
  block it would need.
