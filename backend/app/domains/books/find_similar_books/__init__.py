from app.domains.node_spec import NodeSpec, NodeTier

from .executor import FindSimilarBooksExecutor
from .external import SimilarBooksSearch, SimilarBooksInput, SimilarBooksOutput
from .labels import SimilarBooksNodeTypeEnum

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
