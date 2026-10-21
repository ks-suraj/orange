"""Investigation tools and the executor that mediates every call to them."""

from .base import FaultSpec, Tool, ToolExecutor, ToolResult, ToolStatus
from .dependencies import DependencyGraphTool
from .deployments import ChangeHistoryTool
from .historical_incidents import PastIncidentSearchTool
from .logs import QueryLogsTool
from .metrics import QueryMetricsTool

OBSERVABILITY_TOOLS = ("query_logs", "query_metrics")
DEPENDENCY_TOOLS = ("get_change_history", "get_dependencies", "search_past_incidents")
ALL_TOOLS = OBSERVABILITY_TOOLS + DEPENDENCY_TOOLS


def build_tools() -> dict[str, Tool]:
    tools: list[Tool] = [QueryLogsTool(), QueryMetricsTool(), ChangeHistoryTool(), DependencyGraphTool(), PastIncidentSearchTool()]
    return {t.name: t for t in tools}


__all__ = [
    "ALL_TOOLS",
    "DEPENDENCY_TOOLS",
    "OBSERVABILITY_TOOLS",
    "FaultSpec",
    "Tool",
    "ToolExecutor",
    "ToolResult",
    "ToolStatus",
    "build_tools",
]
