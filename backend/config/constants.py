"""Constants that are not read from the environment: limits, timeouts and paths.

The Makefile and docker-compose.yml hard-code some of the same paths, so a
change here needs the same change there.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

class AppConfig:
    """System-level constants."""

    # NOTE: the token budgets and per-call token caps are env settings, not
    # constants: settings.app.*_TOKEN_BUDGET and settings.openai.MAX_*.

    # Chat messages one IP may send per window, in production. Counted in each
    # instance's memory, so with max-instances=3 the real ceiling is up to 3x
    # this — a brake on one noisy caller, not an exact quota.
    MESSAGES_PER_IP        = 30
    MESSAGES_PER_IP_WINDOW = 60 * 60  # seconds

    # The longest chat message the route accepts, in characters
    MAX_MESSAGE_LENGTH = 2000

    # What a session id in a route's path may look like. Ids come from the URL,
    # so this keeps newlines out of the logs and junk out of the tables; it does
    # not stop a made-up id (the site's daily budget bounds those).
    SESSION_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"

    # Bounds on one feedback row's comment list, which the chat can write in
    # production. The frontend's feedback popup and review editor stop at the
    # same numbers.
    FEEDBACK_MAX_COMMENTS   = 20
    FEEDBACK_COMMENT_LENGTH = 500

    # Firebase App Check's public signing keys. Firebase asks callers to cache
    # them for no more than six hours, which is the lifespan used.
    APP_CHECK_JWKS_URL      = "https://firebaseappcheck.googleapis.com/v1/jwks"
    APP_CHECK_JWKS_LIFESPAN = 6 * 60 * 60

    # The ceiling on any one statement a store runs, in seconds. The engine
    # derives four timeout layers from it (db/README.md).
    # NOTE: DEBIT_TOKENS_TIMEOUT in orchestrator.py must stay above this, since a
    # debit waits for a connection before its statement runs.
    DATABASE_TIMEOUT = 10.0


class OpenAIConstants:
    """The vector-store search size."""

    VECTOR_STORE_MAX_RESULTS = 10    # chunks per search; the API allows 1-50

class FilesLocationConstants:
    """Repository paths resolved from the backend package root."""

    PROJECT_ROOT = PROJECT_ROOT
    ENV_FILE = PROJECT_ROOT / "config" / ".env"

    PROMPTS_DIR = PROJECT_ROOT / "app"
    EXPORT_DIR = PROJECT_ROOT / "logs"
    PAYLOAD_DIR = EXPORT_DIR / "payloads"

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
    # Deliberately permissive: `similarity_score` is recorded on every
    # recommended book in `chat_runs`, so tune this off the real distribution
    # rather than off a guess.
    MIN_SIMILARITY = 0.35

    # books a node fetches for its preview cards
    default_limit = 4
