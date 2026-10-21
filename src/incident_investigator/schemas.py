"""Pydantic models for the structured messages agents exchange, and for the final report.

Every evidence reference is an id of a record returned by a tool (e.g. "L0042", "M07"). Python
validates those ids against the evidence ledger, so agents cannot cite data they never saw.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RootCauseCategory(str, Enum):
    DEPLOYMENT_REGRESSION = "deployment_regression"
    CONFIG_ERROR = "config_error"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    DEPENDENCY_FAILURE = "dependency_failure"
    TRAFFIC_SURGE = "traffic_surge"
    CERTIFICATE_EXPIRY = "certificate_expiry"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"
    OTHER = "other"


SpecialistName = Literal["observability", "dependency"]


def _as_probability(value: float) -> float:
    # Models occasionally answer 85 meaning 0.85; anything else out of range is rejected by the bounds.
    if isinstance(value, (int, float)) and 1 < value <= 100:
        return value / 100
    return value


class IncidentBrief(BaseModel):
    """What investigators are told about the incident. Contains no ground truth."""

    id: str
    title: str
    reported_at: str
    alert: str
    affected_services: list[str]
    window_start: str
    window_end: str

    def render(self) -> str:
        return (
            f"Incident {self.id}: {self.title}\n"
            f"Reported at: {self.reported_at}\n"
            f"Alert: {self.alert}\n"
            f"Alerting services: {', '.join(self.affected_services)}\n"
            f"Telemetry available from {self.window_start} to {self.window_end}; "
            "change history and past incidents cover a longer period."
        )


class TaskRequest(BaseModel):
    key: str | None = Field(None, description="Optional short local id (e.g. 't1') so later tasks in the same list can depend on it.")
    agent: SpecialistName
    objective: str = Field(description="A specific question to answer, naming what to check.")
    focus_services: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list, description="Keys of earlier tasks in this list (or existing task ids) whose findings this task needs first.")


class InvestigationPlan(BaseModel):
    incident_understanding: str
    candidate_explanations: list[str] = Field(default_factory=list)
    tasks: list[TaskRequest] = Field(min_length=1)


class Observation(BaseModel):
    """Something the data directly shows."""

    statement: str
    evidence_ids: list[str] = Field(default_factory=list)


class Inference(BaseModel):
    """A conclusion reasoned from observations."""

    statement: str
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(0.5, ge=0, le=1)

    normalize_confidence = field_validator("confidence", mode="before")(_as_probability)


class AgentFindings(BaseModel):
    summary: str
    observations: list[Observation] = Field(default_factory=list)
    interpretations: list[Inference] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list, description="Tool failures, partial results or data that could not be obtained.")
    suggested_followups: list[str] = Field(default_factory=list)


class Hypothesis(BaseModel):
    id: str
    service: str = Field(description="The single service or component where the fault originates (exact name from the data).")
    category: RootCauseCategory
    mechanism: str = Field(description="How this cause produces the observed symptoms.")
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)

    normalize_confidence = field_validator("confidence", mode="before")(_as_probability)


class HypothesisAnalysis(BaseModel):
    hypotheses: list[Hypothesis] = Field(default_factory=list, description="Competing hypotheses, best first.")
    reasoning: str
    evidence_needed: list[str] = Field(default_factory=list)
    response_to_critique: str | None = None


IssueType = Literal[
    "unsupported_claim",
    "ignored_contradiction",
    "missing_evidence",
    "alternative_not_ruled_out",
    "overconfidence",
    "misread_evidence",
    "other",
]


class CritiqueIssue(BaseModel):
    hypothesis_id: str | None = None
    issue: IssueType
    severity: Literal["material", "minor"] = Field(
        "material",
        description="material: if true, the hypothesis may be the wrong cause; minor: affects precision or confidence only",
    )
    detail: str
    evidence_ids: list[str] = Field(default_factory=list, description="Ledger ids of the evidence behind this objection")


class Critique(BaseModel):
    verdict: Literal["accept", "revise", "investigate"]
    summary: str
    issues: list[CritiqueIssue] = Field(default_factory=list)
    followup_requests: list[TaskRequest] = Field(default_factory=list)


class OrchestratorDecision(BaseModel):
    action: Literal["continue", "stop"]
    rationale: str
    new_tasks: list[TaskRequest] = Field(default_factory=list)


class Remediation(BaseModel):
    action: str
    priority: Literal["immediate", "short_term", "long_term"]
    rationale: str = ""


class ReportDraft(BaseModel):
    """Written by the reporting agent. It explains the system's determination; it does not make it."""

    summary: str
    observed_facts: list[Observation] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    inferred_conclusions: list[Inference] = Field(default_factory=list)
    remediation: list[Remediation] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class BaselineReport(ReportDraft):
    """The single-agent baseline produces hypotheses and the report in one output."""

    hypotheses: list[Hypothesis] = Field(default_factory=list, description="Competing hypotheses, best first.")


class ConclusionDecision(BaseModel):
    """Deterministic conclusive/inconclusive decision, with every criterion it was based on."""

    status: Literal["conclusive", "inconclusive"]
    reasons: list[str]
    top_hypothesis: str | None = None
    top_confidence: float | None = None
    margin_over_runner_up: float | None = None
    verified_support: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    contradiction_share: float | None = None
    blocking_objections: list[str] = Field(default_factory=list, description="Material, evidence-backed critic objections")
    non_blocking_objections: int = 0


class IncidentReport(BaseModel):
    """Final report, assembled and validated by Python from agent outputs."""

    incident_id: str
    system: Literal["multi_agent", "baseline"]
    model: str
    status: Literal["conclusive", "inconclusive"]
    status_reason: str
    decision: ConclusionDecision
    confidence: float
    summary: str
    root_cause: Hypothesis | None
    ranked_hypotheses: list[Hypothesis]
    observed_facts: list[Observation]
    assumptions: list[str]
    inferred_conclusions: list[Inference]
    remediation: list[Remediation]
    open_questions: list[str]
    data_gaps: list[str]
    data_gaps_total: int = 0
    termination_reason: str
