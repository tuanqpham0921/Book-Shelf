from app.domains.node_spec import NodeSpec, NodeTier

from .executor import FindSimilarBooksExecutor
from .labels import SimilarBooksNodeTypeEnum
from .tools import SimilarBooksSearch
from .external import SimilarBooksInput, SimilarBooksOutput

SPEC = NodeSpec(
    node_type=SimilarBooksNodeTypeEnum.REQUEST.value,
    tier=NodeTier.ANALYZE,
    request=SimilarBooksSearch,
    input=SimilarBooksInput,
    output=SimilarBooksOutput,
    executor=FindSimilarBooksExecutor,
)

__all__ = [
    "SPEC",
    "FindSimilarBooksExecutor",
    "SimilarBooksNodeTypeEnum",
    "SimilarBooksInput",
    "SimilarBooksOutput",
    "SimilarBooksSearch",
]
