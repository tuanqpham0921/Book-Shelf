"""The project domain's registered nodes, one `SPEC` per line (same contract as
`books/guide.py`)."""

from app.domains.node_spec import NodeSpec
from app.domains.project import find_project_info

PROJECT_SPECS: tuple[NodeSpec, ...] = (find_project_info.SPEC,)
