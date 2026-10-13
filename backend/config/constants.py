"""Constants that are not read from the environment: limits, budgets, timeouts and paths.

The Makefile and docker-compose.yml hard-code some of the same paths, so a
change here needs the same change there.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

class AppConfig:
    """System-level constants."""

    # What a new session may spend, across every call of every turn. Unlike the
    # per-call caps in OpenAIConstants this is a real budget: it is spent down
    # once per turn and never refills, so when it runs out the deployed service
    # refuses the next message. The sessions table deliberately has no DEFAULT
    # on remaining_tokens — this is the only place the number lives.
    SESSION_TOKEN_BUDGET = 200_000

    # What the whole deployed site may spend in a rolling 24 hours, across
    # every session. The per-session budget above cannot bound this on its own:
    # the session id comes from the URL, so a caller gets a fresh budget by
    # making one up. Production only (token_budget.read_site_spend).
    SITE_DAILY_TOKEN_BUDGET = 3_000_000

    # Chat messages one IP may send per window, in production. Counted in each
    # instance's memory, so with max-instances=3 the real ceiling is up to 3x
    # this — a brake on one noisy caller, not an exact quota.
    MESSAGES_PER_IP        = 30
    MESSAGES_PER_IP_WINDOW = 60 * 60  # seconds

    # The longest chat message the route accepts, in characters
    MAX_MESSAGE_LENGTH = 2000

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
    """Per-call token caps and the vector-store search size."""

    # App wide limit. Guards against a runaway, not a budget: you are billed
    # for tokens generated, so a cap costs nothing until it binds — and when
    # it binds it fails the turn. A node may set a smaller
    # `max_completion_tokens`; above this is refused.
    MAX_INPUT_TOKENS       = 25_000  # whole payload, tool schemas included
    MAX_DEFAULT_COMPLETION = 10_000  # reasoning + visible output together
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
