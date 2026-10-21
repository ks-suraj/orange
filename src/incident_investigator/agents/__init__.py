"""The six agent roles. Each is an LLM prompt + output schema; Python enforces structure and limits."""

from .base import Agent, AgentOutputError, SpecialistAgent, sanitize_citations
from .critic import CriticAgent
from .dependency import DependencyAgent
from .observability import ObservabilityAgent
from .orchestrator import OrchestratorAgent
from .reasoning import ReasoningAgent
from .reporting import ReportingAgent, assemble_report, consolidate_gaps, decide_conclusion

__all__ = [
    "Agent",
    "AgentOutputError",
    "CriticAgent",
    "DependencyAgent",
    "ObservabilityAgent",
    "OrchestratorAgent",
    "ReasoningAgent",
    "ReportingAgent",
    "SpecialistAgent",
    "assemble_report",
    "consolidate_gaps",
    "decide_conclusion",
    "sanitize_citations",
]
