from app.domains.node_spec import NodeSpec, NodeTier

from .executor import FindByNumericTraitsExecutor
from .external import (
    FindByNumericTraitsRetrieval,
    FindByNumericTraitsInput,
    FindByNumericTraitsOutput,
)
from .labels import FindNumericTraitsNodeTypeEnum
from .tools import FindByNumericTraitsArgs

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
