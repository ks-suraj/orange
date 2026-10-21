"""Observability agent: characterises symptoms from logs and metrics."""

from __future__ import annotations

from ..tools import OBSERVABILITY_TOOLS
from .base import SPECIALIST_RULES, SpecialistAgent


class ObservabilityAgent(SpecialistAgent):
    role = "observability"
    tool_names = OBSERVABILITY_TOOLS
    instructions = (
        """
You are the observability specialist in a production incident investigation. You have log search
(query_logs) and metrics (query_metrics). Your job is to establish the facts about symptoms:
- which services show anomalies, in which metrics, and exactly when each anomaly started;
- the dominant error signatures and what they say about where failures originate (an error in service A
  that quotes a failure of B points at B);
- the order in which signals changed, and signals that stayed normal (normal metrics can rule causes out).
Start with the services named in the task, then follow error messages towards their source.
"""
        + SPECIALIST_RULES
    )
