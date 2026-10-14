"""dial — how PlanJane draws a plan: `mermaid.py` turns goals into boxes,
`format.py` turns boxes into a Mermaid string. Import from here."""

# NOTE: dial/ imports nothing from app/ (only airglider), so it can move with
# PlanJane if the planner becomes its own service.
from .format import MermaidBox, get_diagram
from .mermaid import get_goals_mermaid_diagram

__all__ = [
    "get_goals_mermaid_diagram",
    "MermaidBox",
    "get_diagram",
]
