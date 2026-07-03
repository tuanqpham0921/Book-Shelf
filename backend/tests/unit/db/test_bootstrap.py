"""Tests for db/bootstrap.py"""

from unittest.mock import AsyncMock, MagicMock, patch

from common.operation import OperationResult
from db.bootstrap import BootstrapWorkflow, bootstrap_schema
from db.readiness import ReadinessResult


def patch_bootstrap_steps(*, extensions_ok=True, tables_ok=True, indexes_ok=True):
    return (
        patch(
            "db.bootstrap.enable_extensions",
            AsyncMock(return_value=OperationResult(ok=extensions_ok, message="extensions")),
        ),
        patch(
            "db.bootstrap.init_tables",
            AsyncMock(return_value=OperationResult(ok=tables_ok, message="tables")),
        ),
        patch(
            "db.bootstrap.create_indexes",
            AsyncMock(return_value=OperationResult(ok=indexes_ok, message="indexes")),
        ),
    )


class TestBootstrapWorkflow:
    async def test_runs_all_steps_when_no_readiness_given(self):
        ext, tables, indexes = patch_bootstrap_steps()
        with ext, tables, indexes:
            result = await BootstrapWorkflow()(MagicMock())

        assert result.ok is True
        assert result.message == "Bootstrap schema completed."
        assert len(result.steps) == 3

    async def test_skips_all_steps_when_bootstrap_not_needed(self):
        readiness = ReadinessResult(need_db_bootstrap=False)
        ext, tables, indexes = patch_bootstrap_steps()
        with ext as mock_ext, tables as mock_tables, indexes as mock_indexes:
            result = await BootstrapWorkflow()(MagicMock(), readiness=readiness)

        assert result.ok is True
        assert result.message == "No actions required."
        assert result.steps == []
        mock_ext.assert_not_awaited()
        mock_tables.assert_not_awaited()
        mock_indexes.assert_not_awaited()

    async def test_runs_all_steps_when_bootstrap_needed(self):
        readiness = ReadinessResult(need_db_bootstrap=True)
        ext, tables, indexes = patch_bootstrap_steps()
        with ext as mock_ext, tables as mock_tables, indexes as mock_indexes:
            result = await BootstrapWorkflow()(MagicMock(), readiness=readiness)

        assert result.ok is True
        assert len(result.steps) == 3
        mock_ext.assert_awaited_once()
        mock_tables.assert_awaited_once()
        mock_indexes.assert_awaited_once()

    async def test_continues_running_steps_after_a_failure(self):
        ext, tables, indexes = patch_bootstrap_steps(extensions_ok=False)
        with ext, tables as mock_tables, indexes as mock_indexes:
            result = await BootstrapWorkflow()(MagicMock())

        assert result.ok is False
        assert result.message == "Bootstrap schema failed."
        # tables/indexes still ran even though extensions failed
        mock_tables.assert_awaited_once()
        mock_indexes.assert_awaited_once()
        assert len(result.steps) == 3


class TestBootstrapSchema:
    async def test_delegates_to_workflow(self):
        ext, tables, indexes = patch_bootstrap_steps()
        with ext, tables, indexes:
            result = await bootstrap_schema(MagicMock())

        assert result.ok is True
        assert len(result.steps) == 3
