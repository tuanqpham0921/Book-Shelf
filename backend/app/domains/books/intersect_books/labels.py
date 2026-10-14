"""Combine_Intersect's node-type label."""

from enum import Enum


class CombineIntersectNodeTypeEnum(str, Enum):
    """The node's planner-facing name. Output and executor are reached through
    the slice's `NodeSpec`, so they need no label."""

    REQUEST = "Combine_Intersect"
