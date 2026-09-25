from app.domains.node_spec import NodeSpec, NodeTier

from .executor import FindByAuthorExecutor
from .external import FindByAuthorRetrieval, FindByAuthorInput, FindByAuthorOutput
from .labels import FindAuthorNodeTypeEnum

SPEC = NodeSpec(
    node_type=FindAuthorNodeTypeEnum.REQUEST.value,
    tier=NodeTier.RETRIEVAL,
    request=FindByAuthorRetrieval,
    input=FindByAuthorInput,
    output=FindByAuthorOutput,
    executor=FindByAuthorExecutor,
)

__all__ = [
    "SPEC",
    "FindByAuthorExecutor",
    "FindAuthorNodeTypeEnum",
    "FindByAuthorInput",
    "FindByAuthorOutput",
    "FindByAuthorRetrieval",
]
