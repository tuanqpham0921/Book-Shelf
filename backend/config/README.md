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
| `settings.app` | `APP_` | name, environment (`development` / `test` / `production`), CORS origins, Firebase App Check |
| `settings.openai` | `OPENAI_` | API key, model names, embedding size, the project-docs vector store |
| `settings.sqlalchemy` | `POSTGRES_` | host, credentials, pool size, TLS mode |

To add a variable, add a field to the matching class and the value to `config/.env`. Copy `.env.example` to start one. Keys a class does not declare are ignored.

## The two env files

| File | Read by |
|---|---|
| `config/.env` | the app, everywhere it runs locally |
| `config/.env.deployment` | `make deploy`, which turns it into the Cloud Run service and its env (secrets excepted); `make dev-neon` and `make local-prod-neon` read its `POSTGRES_*` lines |

Both are git-ignored. A variable production needs goes in both.

## Constants

`constants.py` holds what is not read from the environment:

- **`AppConfig`**: the token budgets, the per-IP rate limit, message and feedback size caps, App Check keys, and `DATABASE_TIMEOUT`.
- **`OpenAIConstants`**: the per-call token caps and the vector-store search size.
- **`BookConstraints`**: the catalog's bounds (pages, rating, year), the similarity floor and the preview size.
- **`FilesLocationConstants`**: paths, resolved from the backend root.

Use these rather than literals at the call site. Model prices are not here; they live in [airglider](../airglider/README.md).
