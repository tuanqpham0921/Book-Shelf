"""Tests for config/settings/"""

from config.settings import AppSettings, OpenAISettings, Settings, SQLAlchemySettings


def make_sqlalchemy(**overrides) -> SQLAlchemySettings:
    defaults = dict(
        HOST="localhost",
        PORT=5432,
        DB="mydb",
        USER="alice",
        PASSWORD="secret",
        MIN_CONNECTIONS=2,
        MAX_CONNECTIONS=10,
    )
    return SQLAlchemySettings.model_construct(**{**defaults, **overrides})


class TestSQLAlchemySettingsUrl:
    def test_tcp_url_format(self):
        s = make_sqlalchemy(
            HOST="localhost", PORT=5432, DB="mydb", USER="alice", PASSWORD="secret"
        )
        assert (
            s.sqlalchemy_url
            == "postgresql+asyncpg://alice:secret@localhost:5432/mydb?ssl=prefer"
        )

    def test_url_contains_asyncpg_driver(self):
        assert make_sqlalchemy().sqlalchemy_url.startswith("postgresql+asyncpg://")

    def test_url_embeds_credentials(self):
        s = make_sqlalchemy(USER="bob", PASSWORD="hunter2")
        assert "bob:hunter2@" in s.sqlalchemy_url

    def test_url_contains_database_name(self):
        s = make_sqlalchemy(DB="books")
        assert "books" in s.sqlalchemy_url


class TestSQLAlchemySettingsSsl:
    def test_ssl_mode_defaults_to_asyncpg_default(self):
        assert make_sqlalchemy().SSL_MODE == "prefer"

    def test_parameter_is_ssl_not_sslmode(self):
        # asyncpg.connect() takes `ssl=` and has no `sslmode` keyword, and
        # SQLAlchemy's dialect forwards query parameters to it verbatim.
        # Emitting `sslmode` — what Neon's dashboard hands you — raises
        # TypeError at connect time, so assert the spelling, not just the value.
        url = make_sqlalchemy(SSL_MODE="require").sqlalchemy_url
        assert "sslmode=" not in url
        assert url.endswith("?ssl=require")


class TestSQLAlchemySettingsCredentialEscaping:
    def test_password_reserved_characters_are_escaped(self):
        # an unescaped '@' re-points the host: everything left of the LAST '@'
        # is the userinfo, so "p@ss" would make "ss@localhost" the authority
        s = make_sqlalchemy(PASSWORD="p@ss/word#1")
        assert "p%40ss%2Fword%231" in s.sqlalchemy_url
        assert "@localhost:5432/mydb" in s.sqlalchemy_url

    def test_ordinary_credentials_are_left_alone(self):
        # Neon's generated passwords are alphanumeric with underscores, which
        # quote_plus leaves untouched
        s = make_sqlalchemy(USER="neondb_owner", PASSWORD="npg_AbC123xyZ")
        assert "neondb_owner:npg_AbC123xyZ@" in s.sqlalchemy_url


class TestOpenAISettings:
    def test_fields_stored_correctly(self):
        s = OpenAISettings.model_construct(
            API_KEY="sk-test",
            BASE_MODEL="gpt-4o",
            TOKENIZER_ENCODING="cl100k_base",
            EMBEDDING_MODEL="text-embedding-3-small",
            EMBEDDING_DIMENSIONS=1536,
            MAX_CONCURRENCY=5,
        )
        assert s.API_KEY == "sk-test"
        assert s.BASE_MODEL == "gpt-4o"
        assert s.EMBEDDING_DIMENSIONS == 1536
        assert s.MAX_CONCURRENCY == 5


class TestAppSettings:
    def test_fields_stored_correctly(self):
        s = AppSettings.model_construct(
            NAME="book-shelf",
            ENVIRONMENT="test",
            ALLOW_ORIGINS=["http://localhost:3000"],
        )
        assert s.NAME == "book-shelf"
        assert s.ENVIRONMENT == "test"
        assert s.ALLOW_ORIGINS == ["http://localhost:3000"]

    def test_allow_origins_splits_comma_separated_string(self):
        # CORSMiddleware does exact-membership checks on this list; a plain
        # str would substring-match instead, which is a CORS bypass once
        # more than one origin is configured (see field_validator).
        s = AppSettings(
            NAME="book-shelf",
            ENVIRONMENT="test",
            ALLOW_ORIGINS="http://localhost:3000, http://localhost:3001",
        )
        assert s.ALLOW_ORIGINS == ["http://localhost:3000", "http://localhost:3001"]

    def test_allow_origins_accepts_wildcard(self):
        s = AppSettings(NAME="book-shelf", ENVIRONMENT="test", ALLOW_ORIGINS="*")
        assert s.ALLOW_ORIGINS == ["*"]


class TestSettings:
    def test_has_all_sub_settings(self):
        s = Settings.model_construct(
            sqlalchemy=make_sqlalchemy(),
            openai=OpenAISettings.model_construct(
                API_KEY="sk-test",
                BASE_MODEL="gpt-4o",
                TOKENIZER_ENCODING="cl100k_base",
                EMBEDDING_MODEL="text-embedding-3-small",
                EMBEDDING_DIMENSIONS=1536,
                MAX_CONCURRENCY=5,
            ),
            app=AppSettings.model_construct(
                NAME="book-rec",
                ENVIRONMENT="test",
                ALLOW_ORIGINS="*",
            ),
        )
        assert isinstance(s.sqlalchemy, SQLAlchemySettings)
        assert isinstance(s.openai, OpenAISettings)
        assert isinstance(s.app, AppSettings)
