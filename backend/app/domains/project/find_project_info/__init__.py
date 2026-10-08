from app.domains.node_spec import NodeSpec, NodeTier

from .executor import ProjectInfoExecutor, ask_project_docs
from .external import ProjectInfoInput, ProjectInfoOutput, ProjectInfoRequest
from .labels import ProjectInfoNodeTypeEnum
from .tools import ProjectInfoArgs

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
    "ask_project_docs",
    "ProjectInfoArgs",
    "ProjectInfoExecutor",
    "ProjectInfoInput",
    "ProjectInfoNodeTypeEnum",
    "ProjectInfoOutput",
    "ProjectInfoRequest",
]
