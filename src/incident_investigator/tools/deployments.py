"""Deployment, configuration, feature-flag and infrastructure change history."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .base import TimeWindow, Tool, ToolOutput

ChangeType = Literal["deploy", "config_change", "feature_flag", "rollback", "infra"]


class ChangeQuery(TimeWindow):
    service: str | None = Field(None, description="Only changes to this service; omit for all services")
    change_type: ChangeType | None = Field(None, description="Only this kind of change")


class ChangeHistoryTool(Tool):
    name = "get_change_history"
    description = (
        "List deployments, configuration changes, feature-flag changes, rollbacks and infrastructure events "
        "(oldest first). Covers the last 7 days. Filter by service, change_type and time window. A change close "
        "to incident onset is a lead, not proof: check whether what it changed can explain the symptoms."
    )
    Input = ChangeQuery

    def run(self, data: dict[str, Any], q: ChangeQuery) -> ToolOutput:
        records = [
            c
            for c in data["changes"]
            if (q.service is None or c["service"] == q.service)
            and (q.change_type is None or c["type"] == q.change_type)
            and q.in_window(c["ts"])
        ]
        records.sort(key=lambda c: c["ts"])
        return ToolOutput(records=records, note=f"{len(records)} changes")

    def summarize(self, r: dict[str, Any]) -> str:
        version = f" {r['version']}" if r.get("version") else ""
        return f"change {r['ts']} {r['service']} {r['type']}{version} by {r['author']}: {r['description']}"
