"""Retrieve_by_Title's node-type label."""

from enum import Enum


class FindTitleNodeTypeEnum(str, Enum):
    """The node's planner-facing name. Output and executor are reached through
    the slice's `NodeSpec`, so they need no label."""

    REQUEST = "Retrieve_by_Title"
