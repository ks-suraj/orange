import pytest
from pydantic import ValidationError

from incident_investigator.agents.base import extract_json, sanitize_citations
from incident_investigator.schemas import AgentFindings, Hypothesis, InvestigationPlan, RootCauseCategory
from incident_investigator.state import Evidence, EvidenceLedger


def test_confidence_percent_is_normalised():
    h = Hypothesis(id="H1", service="x", category="config_error", mechanism="m", confidence=85)
    assert h.confidence == pytest.approx(0.85)


def test_confidence_out_of_range_rejected():
    with pytest.raises(ValidationError):
        Hypothesis(id="H1", service="x", category="config_error", mechanism="m", confidence=-0.1)


def test_unknown_category_rejected():
    with pytest.raises(ValidationError):
        Hypothesis(id="H1", service="x", category="gremlins", mechanism="m", confidence=0.5)
    assert RootCauseCategory("traffic_surge") is RootCauseCategory.TRAFFIC_SURGE


def test_plan_requires_a_task():
    with pytest.raises(ValidationError):
        InvestigationPlan(incident_understanding="x", tasks=[])


def test_specialist_cannot_be_an_arbitrary_agent():
    with pytest.raises(ValidationError):
        InvestigationPlan(incident_understanding="x", tasks=[{"agent": "reporting", "objective": "o"}])


@pytest.mark.parametrize("text", [
    '{"a": 1}',
    '```json\n{"a": 1}\n```',
    'Here is my answer:\n{"a": 1}\nThanks',
])
def test_extract_json_variants(text):
    assert extract_json(text) == {"a": 1}


def test_extract_json_without_object_raises():
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_sanitize_citations_strips_unknown_ids_recursively():
    ledger = EvidenceLedger()
    ledger.add(Evidence(id="L0001", tool="query_logs", summary="s", record={}, retrieved_by="t", call_id="c"))
    f = AgentFindings(summary="s", observations=[{"statement": "a", "evidence_ids": ["L0001", "L0002", "[L0001]"]}],
                      interpretations=[{"statement": "b", "evidence_ids": ["Z1"], "confidence": 0.5}])
    valid, invalid = sanitize_citations(f, ledger)
    assert (valid, invalid) == (1, 2)
    assert f.observations[0].evidence_ids == ["L0001"]
    assert f.interpretations[0].evidence_ids == []
