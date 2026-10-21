from __future__ import annotations

import pytest

from incident_investigator.config import InvestigationSettings, LLMSettings, Settings
from incident_investigator.scenarios import load_scenario
from incident_investigator.state import EvidenceLedger
from incident_investigator.tools import ToolExecutor, build_tools


@pytest.fixture
def settings() -> Settings:
    # Built directly (not from the environment) so tests never depend on a local .env.
    return Settings(llm=LLMSettings(api_key="test-key"), investigation=InvestigationSettings())


@pytest.fixture
def s01():
    return load_scenario("S01")


@pytest.fixture
def executor_for():
    def make(scenario_id: str, **kwargs) -> ToolExecutor:
        scenario = load_scenario(scenario_id)
        kwargs.setdefault("faults", scenario.faults)
        return ToolExecutor(build_tools(), scenario.data, EvidenceLedger(), **kwargs)
    return make
