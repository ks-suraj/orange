"""Log search over a scenario's application logs."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Literal

from pydantic import Field

from .base import TimeWindow, Tool, ToolOutput

LEVELS = ["DEBUG", "INFO", "WARN", "ERROR"]


class LogQuery(TimeWindow):
    service: str = Field(description="Service name, e.g. checkout-service")
    min_level: Literal["DEBUG", "INFO", "WARN", "ERROR"] = Field("INFO", description="Minimum severity to return")
    contains: str | None = Field(None, description="Case-insensitive substring the message must contain")
    limit: int = Field(20, ge=1, le=50, description="Maximum lines returned")


def _signature(message: str) -> str:
    return re.sub(r"\b[0-9a-f]{6,}\b|\d+", "#", message)[:120]


class QueryLogsTool(Tool):
    name = "query_logs"
    description = (
        "Search application logs of one service. Returns matching log lines (each has an evidence `id`), the total "
        "number of matches, counts by level and the most frequent WARN/ERROR message signatures. When more lines "
        "match than `limit`, the most severe lines are returned first. Use `contains`, `min_level` and a time window "
        "to narrow results."
    )
    Input = LogQuery

    def run(self, data: dict[str, Any], q: LogQuery) -> ToolOutput:
        logs = data["logs"]
        services = sorted({line["service"] for line in logs})
        if q.service not in services:
            return ToolOutput(note=f"No logs for service '{q.service}'. Services with logs: {', '.join(services)}")
        min_rank = LEVELS.index(q.min_level)
        needle = (q.contains or "").lower()
        matches = [
            line
            for line in logs
            if line["service"] == q.service
            and LEVELS.index(line["level"]) >= min_rank
            and q.in_window(line["ts"])
            and needle in line["message"].lower()
        ]
        chosen = sorted(matches, key=lambda l: (-LEVELS.index(l["level"]), l["ts"]))[: q.limit]
        chosen.sort(key=lambda l: l["ts"])
        counts = Counter(line["level"] for line in matches)
        top = Counter(_signature(l["message"]) for l in matches if l["level"] in ("WARN", "ERROR")).most_common(5)
        note = f"{len(matches)} matching lines, {len(chosen)} returned; counts_by_level={dict(counts)}"
        if top:
            note += "; top WARN/ERROR signatures: " + " | ".join(f"{n}x {sig}" for sig, n in top)
        return ToolOutput(records=chosen, note=note)

    def summarize(self, r: dict[str, Any]) -> str:
        return f"log {r['ts']} {r['service']} {r['level']}: {r['message'][:200]}"
