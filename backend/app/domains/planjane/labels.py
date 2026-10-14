"""PlanJane's schema labels: the `node_type` stamped on its tool call and on
each goal. Neither is a registered node — the planner is not in its own
catalog."""

from enum import Enum


# TODO: need to register these
class PlannerNodeTypeEnum(str, Enum):
    PLAN_JANE = "plan_jane"
    SYSTEM_GOAL  = "system_goal"
