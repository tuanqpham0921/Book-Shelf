from typing import Literal
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict
from config.constants import FilesLocationConstants


class SQLAlchemySettings(BaseSettings):
    """Connection and pool settings for the async SQLAlchemy engine (PostgreSQL + asyncpg)."""

    HOST: str
    PORT: int
    DB: str
    USER: str
    PASSWORD: str
    MIN_CONNECTIONS: int
    MAX_CONNECTIONS: int
    # asyncpg's own default, so an unset value connects exactly as before this
    # field existed — the one default here, which keeps every existing .env and
    # the CI env block working. Neon needs `require`; the compose container
    # serves no TLS and falls back to plaintext under `prefer`.
    SSL_MODE: Literal[
        "disable", "allow", "prefer", "require", "verify-ca", "verify-full"
    ] = "prefer"

    @property
    def sqlalchemy_url(self) -> str:
        """Async SQLAlchemy URL (postgresql+asyncpg).

        **`ssl=`, not `sslmode=`.** SQLAlchemy's asyncpg dialect forwards every
        query parameter to `asyncpg.connect()` as a keyword argument, and that
        has `ssl` but no `sslmode` — so Neon's `?sslmode=require` URL, pasted
        as-is, raises `TypeError: connect() got an unexpected keyword argument
        'sslmode'` at connect time.

        Credentials are percent-encoded because Neon generates the password:
        an unescaped `@` re-points the host and a `/` truncates the database
        name, and both fail as a wrong password.
        """
        user = quote_plus(self.USER)
        password = quote_plus(self.PASSWORD)
        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.HOST}:{self.PORT}/{self.DB}?ssl={self.SSL_MODE}"
        )

    model_config = SettingsConfigDict(
        env_file=FilesLocationConstants.ENV_FILE,
        env_prefix="POSTGRES_",
        env_file_encoding="utf-8",
        extra="ignore",
    )
