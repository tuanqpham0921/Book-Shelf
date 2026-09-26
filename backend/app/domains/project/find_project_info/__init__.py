from app.domains.node_spec import NodeSpec, NodeTier

from .executor import ProjectInfoExecutor
from .external import ProjectInfoInput, ProjectInfoOutput, ProjectInfoRequest
from .labels import ProjectInfoNodeTypeEnum

SPEC = NodeSpec(
    node_type=ProjectInfoNodeTypeEnum.REQUEST.value,
    tier=NodeTier.RETRIEVAL,
    request=ProjectInfoRequest,
    input=ProjectInfoInput,
    output=ProjectInfoOutput,
    executor=ProjectInfoExecutor,
)

__all__ = [
    "SPEC",
    "ProjectInfoExecutor",
    "ProjectInfoInput",
    "ProjectInfoNodeTypeEnum",
    "ProjectInfoOutput",
    "ProjectInfoRequest",
]
