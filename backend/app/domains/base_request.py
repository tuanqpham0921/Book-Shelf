"""`BaseRequest`, the base of every node's request schema."""

from pydantic import BaseModel


class BaseRequest(BaseModel):
    """A capability the planner can pick: the docstring is its catalog entry,
    and `node_type` is its name.

    Deliberately fieldless otherwise. The node's arguments live on the slice's
    own `*Args` model in `tools.py`, which the planner never sees.
    """

    # Every concrete request pins this to a Literal of its own node type, and
    # NodeSpec checks it against the spec's name. Typing the base as the flat
    # NodeTypeEnum would mean importing the registry, which imports the slices,
    # which import this module.
    node_type: str
