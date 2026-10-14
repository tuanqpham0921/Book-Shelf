# config

`config` is where BookShelf's backend reads its settings: environment values from `config/.env`, validated by pydantic-settings, and the fixed constants in `constants.py`.

```python
from config import settings, AppConfig, BookConstraints, FilesLocationConstants

settings.app.ENVIRONMENT
settings.openai.EMBEDDING_MODEL
settings.sqlalchemy.sqlalchemy_url
```

## Settings

`settings` is built once, at import. Each sub-settings class reads the variables with its prefix:

| Sub-settings | Prefix | Holds |
|---|---|---|
| `settings.app` | `APP_` | name, environment (`development` / `test` / `production`), CORS origins, Firebase App Check, the session and site-wide token budgets |
| `settings.openai` | `OPENAI_` | API key, model names, embedding size, the project-docs vector store, the per-call token caps |
| `settings.sqlalchemy` | `POSTGRES_` | host, credentials, pool size, TLS mode |

To add a variable, add a field to the matching class and the value to `config/.env`. Copy `.env.example` to start one. Keys a class does not declare are ignored.

## The two env files

| File | Read by |
|---|---|
| `config/.env` | the app, everywhere it runs locally |
| `config/.env.deployment` | `make deploy`, which turns it into the Cloud Run service and its env (secrets excepted); `make dev-neon` and `make local-prod-neon` read its `POSTGRES_*` lines |

Both are git-ignored. A variable production needs goes in both.

## Token limits are internal

`APP_SESSION_TOKEN_BUDGET`, `APP_SITE_DAILY_TOKEN_BUDGET`, `OPENAI_MAX_INPUT_TOKENS` and `OPENAI_MAX_DEFAULT_COMPLETION` are defaulted, so an env file without them still boots; set them to change a limit without a code change. Their values, and the balances measured against them, go to the server log only — never onto a turn's `OperationResult` (sent to the browser as `log_record`), into an error message, or into an SSE event. A user is told a limit was reached, never what it is.

## Constants

`constants.py` holds what is not read from the environment:

- **`AppConfig`**: the per-IP rate limit, message and feedback size caps, App Check keys, and `DATABASE_TIMEOUT`.
- **`OpenAIConstants`**: the vector-store search size.
- **`BookConstraints`**: the catalog's bounds (pages, rating, year), the similarity floor and the preview size.
- **`FilesLocationConstants`**: paths, resolved from the backend root.

Use these rather than literals at the call site. Model prices are not here; they live in [airglider](../airglider/README.md).
