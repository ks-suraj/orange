"""Service dependency graph and health checks."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .base import Tool, ToolOutput


class DependencyQuery(BaseModel):
    service: str = Field(description="Service or component name")
    direction: Literal["dependencies", "dependents", "both"] = Field(
        "both", description="'dependencies' = components this service calls; 'dependents' = services that call it"
    )


class DependencyGraphTool(Tool):
    name = "get_dependencies"
    description = (
        "Return the dependency graph around a service: edges to components it calls ('dependencies') and from "
        "services that call it ('dependents'), plus the latest health-check result for the service and each "
        "neighbour. Health checks may be shallow (e.g. not exercising database writes or TLS)."
    )
    Input = DependencyQuery

    def run(self, data: dict[str, Any], q: DependencyQuery) -> ToolOutput:
        topo = data["topology"]
        known = {e["caller"] for e in topo["edges"]} | {e["callee"] for e in topo["edges"]}
        if q.service not in known:
            return ToolOutput(note=f"Unknown component '{q.service}'. Known: {', '.join(sorted(known))}")
        edges = [
            e
            for e in topo["edges"]
            if (q.direction in ("dependencies", "both") and e["caller"] == q.service)
            or (q.direction in ("dependents", "both") and e["callee"] == q.service)
        ]
        related = {q.service} | {e["caller"] for e in edges} | {e["callee"] for e in edges}
        health = [h for h in topo["health"] if h["service"] in related]
        return ToolOutput(records=edges + health, note=f"{len(edges)} edges, {len(health)} health checks")

    def summarize(self, r: dict[str, Any]) -> str:
        if r["record_type"] == "edge":
            return f"dependency {r['caller']} -> {r['callee']} ({r['kind']})"
        return f"health {r['service']}={r['status']} at {r['checked_at']}: {r['detail']}"
