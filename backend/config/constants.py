from pathlib import Path
""" Centralized constants for the application.
Makefile and docker compose will need to update (manually) if these are changed.
"""

PROJECT_ROOT = Path(__file__).resolve().parent.parent

class AppConfig:
    """System-level constants."""
    SESSION_PREFIX   = "session"

    # What a new session may spend, across every call of every turn. Unlike the
    # per-call caps in OpenAIConstants this is a real budget: it is spent down
    # once per turn and never refills, so when it runs out the deployed service
    # refuses the next message. The sessions table deliberately has no DEFAULT
    # on remaining_tokens — this is the only place the number lives.
    SESSION_TOKEN_BUDGET = 50_000

    # The ceiling on any one statement a store runs, in seconds. Applied by the
    # engine (db/async_engine.py), which derives every layer from it, each one
    # sitting above what it backs up: Postgres' statement_timeout, asyncpg's
    # command_timeout above that, and pool_timeout and the connect timeout for
    # the two waits Postgres cannot see. Enforced there rather than around the
    # await, so a query that runs long is cancelled by the server and the
    # connection survives — cancelling mid-execute leaves it in a state
    # SQLAlchemy no longer knows. Orchestrator.DEBIT_TOKENS_TIMEOUT is one rung
    # further out again, since a debit pays those waits before its statement.
    DATABASE_TIMEOUT = 10.0
    OPENAI_TIMEOUT   = 10.0
    DEFAULT_TIMEOUT  = 10.0


class OpenAIConstants:
    # App wide limit. Guards against a runaway, not a budget: you are billed
    # for tokens generated, so a cap costs nothing until it binds — and when
    # it binds it fails the turn. A node may set a smaller
    # `max_completion_tokens`; above this is refused.
    MAX_INPUT_TOKENS       = 25_000  # whole payload, tool schemas included
    MAX_DEFAULT_COMPLETION = 10_000  # reasoning + visible output together

class FilesLocationConstants:
    """Repository paths resolved from the backend package root."""

    PROJECT_ROOT = PROJECT_ROOT
    DATA_DIR = PROJECT_ROOT / "data"
    # CSV_FILE = "books.csv"
    CSV_FILE = "test_books.csv"
    
    ENV_FILE = PROJECT_ROOT / "config" / ".env"
    
    EXAMPLE_PROMPT_DIR = DATA_DIR / "prompt_example"
    PROMPTS_DIR = PROJECT_ROOT / "app"
    EXPORT_DIR = PROJECT_ROOT / "logs"
    PAYLOAD_DIR = EXPORT_DIR / "payloads"
    
    BACKUP_DIR = DATA_DIR / "backup"
    # the SQL a fresh database is built from — never read by the app, and not
    # in the image; compose mounts it, make neon-bootstrap applies it to Neon
    DB_INIT_DIR = PROJECT_ROOT / "db" / "init"
    SCHEMA_INDEXES_FILE = DB_INIT_DIR / "02_indexes.sql"
    
    LOG_DIR = PROJECT_ROOT / "logs"

class BookConstraints:
    """Domain constraints for book data."""
    MIN_PAGE_COUNT = 4
    MAX_PAGE_COUNT = 3342
    
    MIN_RATING = 0.0
    MAX_RATING = 5.0
    
    MIN_PUBLISHED_YEAR = 1876
    MAX_PUBLISHED_YEAR = 2019

    # How close a book has to sit to the embedded description to count as a
    # candidate at all, as cosine similarity. Without a floor the vector search
    # returns its top N however far away they are — the whole table ordered,
    # truncated — so an ask with no near match comes back full of strangers.
    # Deliberately permissive: enforced now (see `embedding_search_stmt`), and
    # `similarity_score` is recorded on every recommended book in `chat_runs`,
    # so tune this off the real distribution rather than off a guess.
    MIN_SIMILARITY = 0.35

    MIN_LIMIT = 1
    MAX_LIMIT = 5
    default_limit = 4

    def __str__(self):
        """Return string representation of all constraints."""
        result = "BookConstraints:\n"
        
        # Get all class attributes that are constants (uppercase or constraint names)
        constraints = {
            name: value for name, value in self.__class__.__dict__.items()
            if not name.startswith('_') and not callable(value)
        }
        
        for attr_name, attr_value in constraints.items():
            result += f"  {attr_name} = {attr_value}\n"

        return result