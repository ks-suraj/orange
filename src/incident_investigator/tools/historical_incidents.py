"""Keyword search over past incident postmortems."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from .base import Tool, ToolOutput

_STOPWORDS = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "after", "by", "is", "was", "from", "at"}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOPWORDS and len(t) > 1}


class PastIncidentQuery(BaseModel):
    query: str = Field(description="Keywords describing symptoms or a suspected cause")
    service: str | None = Field(None, description="Only incidents involving this service")
    limit: int = Field(5, ge=1, le=10)


class PastIncidentSearchTool(Tool):
    name = "search_past_incidents"
    description = (
        "Search postmortems of past incidents by keyword overlap. Returns the best matches with symptoms, root "
        "cause and resolution. Similar past incidents suggest hypotheses but are not evidence about the current one."
    )
    Input = PastIncidentQuery

    def run(self, data: dict[str, Any], q: PastIncidentQuery) -> ToolOutput:
        wanted = _tokens(q.query)
        scored = []
        for inc in data["past_incidents"]:
            if q.service and q.service not in inc["services"]:
                continue
            text = " ".join([inc["title"], inc["symptoms"], inc["root_cause"], " ".join(inc["services"])])
            score = len(wanted & _tokens(text))
            if score:
                scored.append((score, inc))
        scored.sort(key=lambda s: (-s[0], s[1]["id"]))
        records = [inc for _, inc in scored[: q.limit]]
        return ToolOutput(records=records, note=f"{len(scored)} incidents matched; {len(records)} returned")

    def summarize(self, r: dict[str, Any]) -> str:
        return f"past incident {r['date']} '{r['title']}' ({', '.join(r['services'])}); root cause: {r['root_cause']}"
