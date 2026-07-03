"""Tests for db/readiness.py"""

from unittest.mock import AsyncMock, MagicMock, patch

from common.operation import OperationResult
from db.readiness import (
    ReadinessResult,
    ReadinessWorkflow,
    _check_table,
    _check_table_extensions,
    _check_table_rows,
    is_ready,
)


def make_session(scalar_value=None, rows=None):
    """Build a mock AsyncSession whose execute() result yields scalar_value/rows."""
    mock_result = MagicMock()
    mock_result.scalar.return_value = scalar_value
    mock_result.fetchall.return_value = rows or []

    session = AsyncMock()
    session.execute.return_value = mock_result
    return session


def make_session_factory(session):
    """Build a session_factory whose `async with factory() as session` yields `session`."""
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


class TestCheckTable:
    async def test_ok_when_table_exists(self):
        session = make_session(scalar_value=True)
        result = await _check_table(session, schema="public", table="books")
        assert result.ok is True
        assert "exists" in result.message

    async def test_not_ok_when_table_missing(self):
        session = make_session(scalar_value=False)
        result = await _check_table(session, schema="public", table="books")
        assert result.ok is False
        assert "not found" in result.message


class TestCheckTableRows:
    async def test_ok_when_enough_rows(self):
        session = make_session(scalar_value=100)
        result = await _check_table_rows(session, schema="public", table="books", min_rows=10)
        assert result.ok is True
        assert result.output == 100

    async def test_not_ok_when_too_few_rows(self):
        session = make_session(scalar_value=1)
        result = await _check_table_rows(session, schema="public", table="books", min_rows=10)
        assert result.ok is False


class TestCheckTableExtensions:
    async def test_ok_when_all_extensions_installed(self):
        session = make_session(rows=[("vector",), ("pg_trgm",)])
        result = await _check_table_extensions(session)
        assert result.ok is True
        assert result.output["missing"] == []

    async def test_not_ok_when_extension_missing(self):
        session = make_session(rows=[("vector",)])
        result = await _check_table_extensions(session)
        assert result.ok is False
        assert result.output["missing"] == ["pg_trgm"]


def patch_readiness_checks(
    *,
    connected: bool = True,
    table_ok: bool = True,
    rows_ok: bool = True,
    extensions_ok: bool = True,
    num_missing_embeddings: int = 0,
):
    """Patch every dependency ReadinessWorkflow.run() calls out to."""
    table_result = OperationResult(name="table", ok=table_ok, message="table check")
    rows_result = OperationResult(name="rows", ok=rows_ok, message="rows check", output=42)
    extensions_result = OperationResult(
        name="extensions",
        ok=extensions_ok,
        message="extensions check",
        output={"missing": [] if extensions_ok else ["pg_trgm"]},
    )

    book_store = MagicMock()
    book_store.get_num_book_missing_embeddings = AsyncMock(return_value=num_missing_embeddings)

    return (
        patch("db.readiness.check_connection", AsyncMock(return_value=connected)),
        patch("db.readiness._check_table", AsyncMock(return_value=table_result)),
        patch("db.readiness._check_table_rows", AsyncMock(return_value=rows_result)),
        patch("db.readiness._check_table_extensions", AsyncMock(return_value=extensions_result)),
        patch("db.readiness.BookStore", return_value=book_store),
    )


class TestReadinessWorkflow:
    async def test_all_checks_pass(self):
        patches = patch_readiness_checks()
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = await ReadinessWorkflow()(
                make_session_factory(make_session()), schema="public", table="books", min_rows=10
            )

        assert result.ok is True
        assert result.message == "Database is ready."
        assert isinstance(result.output, ReadinessResult)
        assert result.output.database_connected is True
        assert result.output.need_db_bootstrap is False
        assert result.output.enough_rows is True
        assert result.output.need_extensions is False
        assert result.output.num_missing_embeddings == 0
        assert len(result.steps) == 4

    async def test_connection_failure_short_circuits_and_reports_failure(self):
        patches = patch_readiness_checks(connected=False)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = await ReadinessWorkflow()(
                make_session_factory(make_session()), schema="public", table="books", min_rows=10
            )

        assert result.ok is False
        assert result.run_time_error is not None
        assert "Database connection failed" in result.message
        # none of the per-table checks should have run
        assert result.steps == []

    async def test_missing_table_marks_need_db_bootstrap_but_keeps_running(self):
        patches = patch_readiness_checks(table_ok=False)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = await ReadinessWorkflow()(
                make_session_factory(make_session()), schema="public", table="books", min_rows=10
            )

        assert result.ok is False
        assert result.message == "Database is not ready."
        assert result.output.need_db_bootstrap is True
        # all four steps still ran despite the first one failing
        assert len(result.steps) == 4

    async def test_missing_embeddings_marks_step_and_overall_failure(self):
        patches = patch_readiness_checks(num_missing_embeddings=5)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = await ReadinessWorkflow()(
                make_session_factory(make_session()), schema="public", table="books", min_rows=10
            )

        assert result.ok is False
        assert result.output.num_missing_embeddings == 5
        embeddings_step = next(s for s in result.steps if s.name == "num_missing_embeddings")
        assert embeddings_step.ok is False

    async def test_is_ready_delegates_to_workflow(self):
        patches = patch_readiness_checks()
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = await is_ready(
                make_session_factory(make_session()), schema="public", table="books", min_rows=10
            )

        assert result.ok is True
        assert isinstance(result.output, ReadinessResult)
