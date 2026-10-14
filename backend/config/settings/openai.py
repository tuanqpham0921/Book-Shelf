"""OpenAI settings (`OPENAI_*`): the API key, model names and the docs vector store."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from config.constants import FilesLocationConstants


class OpenAISettings(BaseSettings):
    API_KEY: str
    BASE_MODEL: str

    EMBEDDING_MODEL: str
    EMBEDDING_DIMENSIONS: int
    MAX_CONCURRENCY: int
    # BookShelf's docs, searched by find_project_info. Unset, every project
    # lookup fails and the message falls through to the planner.
    VECTOR_STORE_ID: str | None = None

    # Per-call caps, app wide. Guards against a runaway, not a budget: you are
    # billed for tokens generated, so a cap costs nothing until it binds — and
    # when it binds it fails the call. A node may set a smaller
    # `max_completion_tokens`; above this is refused. Internal, like the
    # budgets on AppSettings: neither number is put in an error message.
    MAX_INPUT_TOKENS: int = 25_000        # whole payload, tool schemas included
    MAX_DEFAULT_COMPLETION: int = 10_000  # reasoning + visible output together

    model_config = SettingsConfigDict(
        env_file=FilesLocationConstants.ENV_FILE,
        env_prefix="OPENAI_",
        env_file_encoding="utf-8",
        extra="ignore",
    )
