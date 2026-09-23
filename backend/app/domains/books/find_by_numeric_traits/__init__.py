from app.domains.node_spec import NodeSpec, NodeTier

from .executor import FindByNumericTraitsExecutor
from .labels import FindNumericTraitsNodeTypeEnum
from .schemas import FindByNumericTraitsArgs, FindByNumericTraitsRetrieval
from .external import FindByNumericTraitsInput, FindByNumericTraitsOutput

SPEC = NodeSpec(
    node_type=FindNumericTraitsNodeTypeEnum.REQUEST.value,
    tier=NodeTier.RETRIEVAL,
    request=FindByNumericTraitsRetrieval,
    input=FindByNumericTraitsInput,
    output=FindByNumericTraitsOutput,
    executor=FindByNumericTraitsExecutor,
)

__all__ = [
    "SPEC",
    "FindByNumericTraitsArgs",
    "FindByNumericTraitsExecutor",
    "FindNumericTraitsNodeTypeEnum",
    "FindByNumericTraitsInput",
    "FindByNumericTraitsOutput",
    "FindByNumericTraitsRetrieval",
]
