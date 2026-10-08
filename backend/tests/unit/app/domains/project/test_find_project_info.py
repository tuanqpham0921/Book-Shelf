"""The project-info node: how the docs service's stream is read, and the flow
with the one outside call faked.

Only `ask_project_docs` is faked — there is no store and no LLM call — so the
executor, its `@task` envelope and `finalize_result` are all real.
"""

from unittest.mock import AsyncMock, patch

import pytest

from airglider import OperationResult, Response
from app.domains.node_spec import NodeTier
from app.domains.project.find_project_info import (
    ProjectInfoExecutor,
    ProjectInfoInput,
)
from app.domains.project.find_project_info.executor import join_sse_data
from app.registry import REGISTRY


class TestJoinSseData:
    def test_deltas_are_joined_in_order(self):
        lines = ["data: ", "", "data: Book", "", "data: Shelf", "", "data:  uses", ""]

        assert join_sse_data(lines) == "BookShelf uses"

    def test_a_multi_line_event_is_a_newline(self):
        # how the service sends "\n\n" inside one delta
        lines = ["data: :", "data: ", "data: ", "", "data: -", ""]

        assert join_sse_data(lines) == ":\n\n-"

    def test_a_last_event_with_no_blank_line_is_kept(self):
        assert join_sse_data(["data: a", "", "data: b"]) == "ab"


def test_it_is_registered_as_a_retrieval():
    spec = REGISTRY.spec("Retrieve_Project_Info")

    assert spec is not None
    assert spec.executor is ProjectInfoExecutor
    assert spec.tier is NodeTier.RETRIEVAL


class TestTheFlow:
    @pytest.mark.asyncio
    async def test_it_asks_the_docs_the_instruction(self, request_context):
        node = ProjectInfoExecutor(request_context)
        docs = AsyncMock(return_value=OperationResult(ok=True, response=Response(result="It's on GitHub.")))

        with patch(
            "app.domains.project.find_project_info.executor.ask_project_docs", docs
        ):
            result = await node(ProjectInfoInput(instruction="Find the GitHub repo"))

        assert result.ok, result.runtime_error
        docs.assert_awaited_once_with("Find the GitHub repo")
        out = result.unwrap()
        assert out.question == "Find the GitHub repo"
        assert out.answer == "It's on GitHub."

    @pytest.mark.asyncio
    async def test_a_failed_lookup_fails_the_node(self, request_context):
        node = ProjectInfoExecutor(request_context)
        docs = AsyncMock(return_value=OperationResult(ok=False))

        with patch(
            "app.domains.project.find_project_info.executor.ask_project_docs", docs
        ):
            result = await node(ProjectInfoInput(instruction="Find the GitHub repo"))

        assert not result.ok
