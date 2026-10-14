"""Analyze_Similar_Books' node-type label."""

from enum import Enum


class SimilarBooksNodeTypeEnum(str, Enum):
    """The node's planner-facing name. Output and executor are reached through
    the slice's `NodeSpec`, so they need no label."""

    REQUEST = "Analyze_Similar_Books"
