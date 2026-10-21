"""Loading synthetic incident scenarios from data/incidents/<id>/.

A scenario is the telemetry the tools serve plus the fault-injection config. Ground truth lives
in a separate directory (data/ground_truth/) that only the evaluation code reads.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .config import DATA_DIR
from .schemas import IncidentBrief
from .tools.base import FaultSpec

DATA_FILES = {
    "logs": "logs.json",
    "metrics": "metrics.json",
    "changes": "changes.json",
    "topology": "topology.json",
    "past_incidents": "past_incidents.json",
}


class Scenario(BaseModel):
    brief: IncidentBrief
    faults: list[FaultSpec] = Field(default_factory=list)
    data: dict[str, Any]


def scenario_ids(data_dir: Path = DATA_DIR) -> list[str]:
    root = data_dir / "incidents"
    return sorted(p.name for p in root.iterdir() if (p / "scenario.json").is_file())


def load_scenario(scenario_id: str, data_dir: Path = DATA_DIR) -> Scenario:
    folder = data_dir / "incidents" / scenario_id
    meta = json.loads((folder / "scenario.json").read_text(encoding="utf-8"))
    data = {key: json.loads((folder / name).read_text(encoding="utf-8")) for key, name in DATA_FILES.items()}
    return Scenario(brief=IncidentBrief(**meta["brief"]), faults=meta.get("faults", []), data=data)
