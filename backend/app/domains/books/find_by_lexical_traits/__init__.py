"""Retrieve_by_Lexical_Traits slice: exports the node's `SPEC`."""

from app.domains.node_spec import NodeSpec, NodeTier

from .executor import FindByLexicalTraitsExecutor
from .external import (
    FindByLexicalTraitsInput,
    FindByLexicalTraitsOutput,
    FindByLexicalTraitsRetrieval,
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
