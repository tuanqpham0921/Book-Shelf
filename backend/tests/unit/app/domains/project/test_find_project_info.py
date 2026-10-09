"""The project-info node: the check request, and the flow with its two
outside calls faked.

Only the vector-store search and the LLM call are faked — there is no store —
so the executor, its `@task` envelope and `finalize_result` are all real.
"""

from unittest.mock import AsyncMock, patch

import pytest

from openai.types import VectorStoreSearchResponse
from openai.types.vector_store_search_response import Content

from app.domains.node_spec import NodeTier
from app.domains.project.find_project_info import (
    ProjectInfoExecutor,
    ProjectInfoInput,
)
from app.domains.project.find_project_info.executor import build_answer_request
from app.domains.project.find_project_info.tools import ProjectDocsAnswer
from app.registry import REGISTRY

CHUNKS = "SOURCE: docs/deployment.md (score: 0.564)\nCloud Run"


def test_it_is_registered_as_a_retrieval():
    spec = REGISTRY.spec("Retrieve_Project_Info")

    assert spec is not None
    assert spec.executor is ProjectInfoExecutor
    assert spec.tier is NodeTier.RETRIEVAL


class TestBuildAnswerRequest:
    def test_the_question_and_the_chunks_are_both_sent(self):
        req = build_answer_request("How is it deployed?", CHUNKS)

        [message] = req.messages
        assert "How is it deployed?" in message.content
        assert CHUNKS in message.content
        assert req.tool_models == [ProjectDocsAnswer]

    def test_no_question_is_refused(self):
        with pytest.raises(ValueError):
            build_answer_request("", CHUNKS)


def _hit(filename: str, score: float, *texts: str) -> VectorStoreSearchResponse:
    return VectorStoreSearchResponse(
        file_id="file_1",
        filename=filename,
        score=score,
        attributes=None,
        content=[Content(type="text", text=t) for t in texts],
    )


def _run(request_context, hits, checked):
    request_context.llm_client.search_vector_store = AsyncMock(return_value=hits)
    node = ProjectInfoExecutor(request_context)
    node.run_llm_args_parse = AsyncMock(return_value=checked)
    return node


class TestTheFlow:
    @pytest.mark.asyncio
    async def test_a_supported_answer_is_kept_with_its_sources(self, request_context):
        node = _run(
            request_context,
            [_hit("docs/deployment.md", 0.5642, "Cloud ", "Run")],
            ProjectDocsAnswer(
                supported=True, answer="On Cloud Run.", sources=["docs/deployment.md"]
            ),
        )

        result = await node(ProjectInfoInput(instruction="How is it deployed?"))

        assert result.ok, result.runtime_error
        request_context.llm_client.search_vector_store.assert_awaited_once_with(
            "How is it deployed?"
        )
        out = result.unwrap()
        assert out.question == "How is it deployed?"
        assert out.answer == "On Cloud Run."
        assert out.sources == ["docs/deployment.md"]

    @pytest.mark.asyncio
    async def test_hits_are_sent_as_source_lines_between_rules(self, request_context):
        node = _run(
            request_context,
            [_hit("a.md", 0.9, "first"), _hit("b.md", 0.25, "second")],
            ProjectDocsAnswer(supported=True, answer="Yes.", sources=["a.md"]),
        )

        await node(ProjectInfoInput(instruction="Anything?"))

        [req] = node.run_llm_args_parse.await_args.args
        assert (
            "SOURCE: a.md (score: 0.900)\nfirst\n\n---\n\n"
            "SOURCE: b.md (score: 0.250)\nsecond"
        ) in req.messages[0].content

    @pytest.mark.asyncio
    async def test_chunks_that_do_not_answer_are_rejected(self, request_context):
        node = _run(
            request_context,
            [_hit("docs/deployment.md", 0.56, "Cloud Run")],
            ProjectDocsAnswer(
                supported=False, answer="Not stated.", sources=["docs/deployment.md"]
            ),
        )

        result = await node(ProjectInfoInput(instruction="Who is Tuan's cat?"))

        assert not result.ok
        assert node.result.answer == ""
        assert node.result.sources == []

    @pytest.mark.asyncio
    async def test_no_hits_fails_the_node(self, request_context):
        node = _run(request_context, [], None)

        result = await node(ProjectInfoInput(instruction="How is it deployed?"))

        assert not result.ok
        node.run_llm_args_parse.assert_not_awaited()
