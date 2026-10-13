"""`NodeSpec`, one per node and the only thing `app/registry.py` reads, and
`NodeTier`, the catalog's sections."""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from app.domains.node_input import NodeInput, WorkflowInput

if TYPE_CHECKING:
    from app.domains.base_workflow import AppWorkflow, NodeWorkflowOutput
    from app.domains.base_request import BaseRequest


class NodeTier(str, Enum):
    """Catalog grouping. The value is the section heading the planner LLM
    reads in `Registry.format_catalog()`, so it is prompt text."""

    RETRIEVAL = "Retrieval — lookup or fetch data"
    COMBINE = "Combine — narrow or merge what earlier goals found, without searching again"
    ANALYZE = "Analyze — interpret, compare, or recommend using retrieved data"


@dataclass(frozen=True)
class NodeSpec:
    """Everything the system needs to know about one node.

    Three schemas, distinguished by who fills them in: `request` by the planner
    LLM, `input` by the task runner, `output` by the executor. (`request` and
    `input` converge eventually — the parsed args are an input the node
    currently produces for itself.)

    Args:
        node_type: The capability name the planner emits, e.g. "Retrieve_by_Title".
        tier: Which catalog section this node is listed under.
        request: The pydantic request schema — but what the registry uses it
            for is its *docstring*, which IS the catalog entry the planner
            LLM reads. It lives in the slice's `external.py`. The arguments a
            node needs are not on it: each slice declares an `*Args` model in
            `tools.py` that its own parse call ships, so the planner is given
            a capability to pick rather than fields to guess at. The request
            stays a model because it carries the `node_type` Literal
            everything discriminates on — and so a field the planner really
            should fill has somewhere to go.
        input: What this node is invoked with — declares which upstream shapes
            it can consume. The default accepts the goal text and nothing else,
            which is the right contract for a node with no dependencies.
        output: The result payload the executor fills in.
        executor: The workflow that runs it. None for a node that is registered
            for planning but not yet runnable.
    """

    node_type: str
    tier: NodeTier
    request: type["BaseRequest"]
    output: type["NodeWorkflowOutput"]
    executor: type["AppWorkflow"] | None = None
    input: type[WorkflowInput] = NodeInput

    def __post_init__(self) -> None:
        field = self.request.model_fields.get("node_type")
        declared = field.default if field is not None else None
        value = declared.value if isinstance(declared, Enum) else declared
        if value != self.node_type:
            raise ValueError(
                f"NodeSpec({self.node_type!r}) disagrees with "
                f"{self.request.__name__}.node_type default ({value!r}) — the "
                "planner emits the spec's name but pydantic discriminates on "
                "the schema's, so a mismatch makes the node unreachable"
            )
