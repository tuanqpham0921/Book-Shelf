"""Triage — whether a turn gets planned at all.

`external.py` holds what the layers around it read back (`TriageOutput`,
`QueryPortion`, `TriageVerdict`); `tools.py` holds what the decomposition's
LLM fills in; `executor.py` runs; `cache.py` is the dev plan replay. Import
from this package root rather than any of them.
"""

from .executor import TriageWorkflow
from .external import QueryPortion, TriageOutput, TriageVerdict

__all__ = ["TriageWorkflow", "TriageOutput", "QueryPortion", "TriageVerdict"]
