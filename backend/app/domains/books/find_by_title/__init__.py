from app.domains.node_spec import NodeSpec, NodeTier

from .executor import FindByTitleExecutor
from .external import FindByTitleRetrieval, FindByTitleInput, FindByTitleOutput
from .labels import FindTitleNodeTypeEnum

SPEC = NodeSpec(
    node_type=FindTitleNodeTypeEnum.REQUEST.value,
    tier=NodeTier.RETRIEVAL,
    request=FindByTitleRetrieval,
    input=FindByTitleInput,
    output=FindByTitleOutput,
    executor=FindByTitleExecutor,
)

__all__ = [
    "SPEC",
    "FindByTitleExecutor",
    "FindTitleNodeTypeEnum",
    "FindByTitleInput",
    "FindByTitleOutput",
    "FindByTitleRetrieval",
]
