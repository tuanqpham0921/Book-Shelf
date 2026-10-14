"""App settings (`APP_*`): name, environment, CORS origins and App Check."""

from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from config.constants import FilesLocationConstants


class AppSettings(BaseSettings):
    NAME: str
    # a closed set so a typo ("prod") fails at boot rather than falling through
    # the string comparisons that gate every disk write
    ENVIRONMENT: Literal["development", "test", "production"]
    # NoDecode: pydantic-settings otherwise tries to JSON-decode env values
    # for list-typed fields before validators run, which breaks on a plain
    # comma-separated string. The field_validator below does the real split.
    ALLOW_ORIGINS: Annotated[list[str], NoDecode]
    # Firebase App Check is enforced exactly when this is set — the token's
    # audience and issuer are both built from it, so it is the one value the
    # check needs. The deploy recipe sets it; local dev leaves it unset, since
    # a Vite dev server has no reCAPTCHA key to earn a token with.
    FIREBASE_PROJECT_NUMBER: str | None = None

    # The token budgets. Internal: they are logged, never recorded on the turn's
    # trace or sent to the browser — a user is told a budget ran out, not its size.
    # Defaulted so an .env without them (CI, an old local file) still boots.
    #
    # What a new session may spend, across every call of every turn. A real
    # budget, unlike the per-call caps on OpenAISettings: it is spent down once
    # per turn and never refills. The sessions table deliberately has no
    # DEFAULT on remaining_tokens — this is the only place the number lives.
    SESSION_TOKEN_BUDGET: int = 200_000
    # What the whole site may spend in a rolling 24 hours, across every session.
    # The session budget cannot bound this on its own: the session id comes from
    # the URL, so a caller gets a fresh budget by making one up. Production only
    # (token_budget.read_site_spend).
    SITE_DAILY_TOKEN_BUDGET: int = 3_000_000

    model_config = SettingsConfigDict(
        env_file=FilesLocationConstants.ENV_FILE,
        env_prefix="APP_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("ALLOW_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, value):
        # CORSMiddleware does exact-membership checks against this list; a
        # plain str would do substring matching instead, which is a CORS
        # bypass once more than one origin is configured. Env var stays a
        # comma-separated string; this splits it before it reaches Settings.
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value
