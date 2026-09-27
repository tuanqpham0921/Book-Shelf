from app.domains.node_spec import NodeSpec, NodeTier

from .executor import FindByLexicalTraitsExecutor
from .external import (
    FindByLexicalTraitsRetrieval,
    FindByLexicalTraitsInput,
    FindByLexicalTraitsOutput,
)
from .labels import FindLexicalTraitsNodeTypeEnum
from .tools import FindByLexicalTraitsArgs

SPEC = NodeSpec(
    node_type=FindLexicalTraitsNodeTypeEnum.REQUEST.value,
    tier=NodeTier.RETRIEVAL,
    request=FindByLexicalTraitsRetrieval,
    input=FindByLexicalTraitsInput,
    output=FindByLexicalTraitsOutput,
    executor=FindByLexicalTraitsExecutor,
)

__all__ = [
    "SPEC",
    "FindByLexicalTraitsArgs",
    "FindByLexicalTraitsExecutor",
    "FindByLexicalTraitsInput",
    "FindByLexicalTraitsOutput",
    "FindByLexicalTraitsRetrieval",
    "FindLexicalTraitsNodeTypeEnum",
]
