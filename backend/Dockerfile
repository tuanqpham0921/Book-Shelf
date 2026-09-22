# Build context is backend/. Deployed by `make deploy` (gcloud run deploy
# --source), which hands this file to Cloud Build — see docs/deploy.md.

FROM python:3.12-slim AS deps

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    PIP_NO_CACHE_DIR=1
RUN pip install poetry

WORKDIR /app
COPY pyproject.toml poetry.lock ./
# --no-root: the app runs from source (WORKDIR is on sys.path, same as
# `make dev`), so installing the project itself would be dead weight.
RUN poetry install --only main --no-root


FROM python:3.12-slim AS runtime

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TIKTOKEN_CACHE_DIR=/app/.tiktoken \
    PORT=8080

WORKDIR /app
COPY --from=deps /app/.venv /app/.venv

# tiktoken fetches its BPE ranks over the network on first use
# (clients/openai_client.py, lazily imported inside token_count). Bake them in
# so a cold instance doesn't call openaipublic.blob.core.windows.net on its
# first embedding. cl100k_base backs text-embedding-3-large; o200k_base is
# OPENAI_TOKENIZER_ENCODING.
RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base'); tiktoken.get_encoding('o200k_base')"

# An explicit whitelist, not `COPY . .`: logs/, data/, evals/, playground/ and
# tests/ cannot enter the image even if .dockerignore drifts. Copying whole
# directories also carries the prompt .txt templates that
# app/common/prompt_loader.py reads at runtime — a *.py pattern would drop them
# and fail on the first request rather than at boot.
COPY airglider ./airglider
COPY app       ./app
COPY clients   ./clients
COPY common    ./common
COPY config    ./config
COPY db        ./db

# No chown: /app stays root-owned and world-readable, so the app can read it
# but not write it. Cloud Run's filesystem is in-memory — a stray write should
# fail loudly, not quietly eat instance RAM. (A `chown -R` here would also
# rewrite every file into a new ~190MB layer.) This is also why the image only
# boots as APP_ENVIRONMENT=production: development's log file needs /app/logs.
RUN useradd --create-home --uid 1000 app
USER app

EXPOSE 8080
# `sh -c` so ${PORT} expands (Cloud Run injects it); `exec` replaces the shell
# so uvicorn is PID 1, SIGTERM reaches it and in-flight SSE streams close
# cleanly. One worker: Cloud Run runs one process per container and scales by
# instance.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
