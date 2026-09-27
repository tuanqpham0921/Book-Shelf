"""Project-domain guide: the specs of every node this domain offers.

Same contract as `books/guide.py`: one line per node, `Registry`
(app/registry.py) answers everything else from these, and dropping a SPEC here
parks the node.
"""

from app.domains.node_spec import NodeSpec
from app.domains.project import find_project_info

PROJECT_SPECS: tuple[NodeSpec, ...] = (find_project_info.SPEC,)
