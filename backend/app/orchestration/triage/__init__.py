"""Triage — whether a turn gets planned at all.

`external.py` holds what the layers around it read back (`TriageOutput`);
`tools.py` holds the `PlanJane` tool its LLM can pick; `executor.py` runs;
`cache.py` is the dev plan replay. Import from this package root rather than
any of them.
"""

from .executor import TriageWorkflow
from .external import TriageOutput

__all__ = ["TriageWorkflow", "TriageOutput"]
