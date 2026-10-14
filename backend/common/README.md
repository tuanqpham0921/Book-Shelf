# common

`common` holds the backend's process-wide helpers, used by the app and by the scripts beside it (evals, tests). App-specific shared code lives in `app/common/` instead.

| Module | What it does |
|---|---|
| `context.py` | `AppContext`: the database engine, session factory and OpenAI client, built once at startup and closed at shutdown |
| `setup_logging.py` | Rich console logs in local development, plain lines elsewhere (Cloud Logging parses them), and `logs/dev_log.log` in development. `LOG_LEVEL` sets the level |
| `pydantic_validators.py` | `bounded_float` and `bounded_string`, lenient validators for LLM-filled fields: a bad value is clamped or replaced, never rejected |
| `utils/` | file helpers (`save_file`, `save_text`, `load_json`) and the serialization helpers re-exported from airglider |

`print_json` in `utils/` is for debugging: it pretty-prints anything airglider can serialize, a record or a model included.
