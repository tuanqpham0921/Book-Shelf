"""The project-info node: which facts a parse selects, and the flow with the
one LLM call faked.

Nothing else is faked — there is no store to fake — so the executor, its
`@task` envelope and `finalize_result` are all real.
"""

from unittest.mock import AsyncMock

import pytest

from app.domains.node_spec import NodeTier
from app.domains.project.find_project_info import (
    ProjectInfoExecutor,
    ProjectInfoInput,
)
from app.domains.project.find_project_info.executor import (
    PROJECT_INFO,
    build_arg_parser_request,
    select_project_info,
)
from app.domains.project.find_project_info.tools import (
    ProjectInfoArgs,
    ProjectInfoField,
)
from app.registry import REGISTRY


class TestSelectProjectInfo:
    def test_every_field_but_all_has_a_fact(self):
        # a field the parse can pick with no entry would be silently dropped
        assert set(PROJECT_INFO) == set(ProjectInfoField) - {ProjectInfoField.ALL}

    def test_it_returns_only_the_fields_asked_for(self):
        info = select_project_info([ProjectInfoField.TECHNOLOGY_STACK])

        assert list(info) == ["technology_stack"]

    @pytest.mark.parametrize(
        "fields", [[ProjectInfoField.ALL], [ProjectInfoField.NAME, ProjectInfoField.ALL], []]
    )
    def test_all_or_nothing_parsed_is_every_fact(self, fields):
        assert list(select_project_info(fields)) == [f.value for f in PROJECT_INFO]

    def test_order_follows_the_facts_not_the_parse(self):
        info = select_project_info(
            [ProjectInfoField.PROJECT_URL, ProjectInfoField.NAME, ProjectInfoField.NAME]
        )

        assert list(info) == ["name", "project_url"]


def test_an_empty_instruction_is_refused():
    with pytest.raises(ValueError):
        build_arg_parser_request("")


def test_it_is_registered_as_a_retrieval():
    spec = REGISTRY.spec("Retrieve_Project_Info")

    assert spec is not None
    assert spec.executor is ProjectInfoExecutor
    assert spec.tier is NodeTier.RETRIEVAL


class TestTheFlow:
    @pytest.mark.asyncio
    async def test_it_looks_up_the_parsed_fields(self, request_context):
        node = ProjectInfoExecutor(request_context)
        args = ProjectInfoArgs(fields=[ProjectInfoField.PROJECT_GITHUB_REPO_URL])
        node.run_llm_args_parse = AsyncMock(return_value=args)

        result = await node(ProjectInfoInput(instruction="Find the GitHub repo"))

        assert result.ok, result.runtime_error
        out = result.unwrap()
        assert out.args == args
        assert out.info == {
            "project_github_repo_url": PROJECT_INFO[ProjectInfoField.PROJECT_GITHUB_REPO_URL]
        }
