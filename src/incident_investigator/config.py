"""Runtime configuration loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RESULTS_DIR = PROJECT_ROOT / "results"


class LLMSettings(BaseModel):
    provider: str = "openrouter"
    model: str = "anthropic/claude-haiku-5.5"
    api_key: str | None = Field(default=None, repr=False)
    base_url: str = "https://openrouter.ai/api/v1"
    max_tokens: int = 4096
    reasoning_effort: str | None = "low"
    timeout_s: float = 120.0
    max_retries: int = 3
    structured_outputs: bool = True  # provider-side JSON-schema constrained decoding for tool-less agent calls


class InvestigationSettings(BaseModel):
    """Limits and decision thresholds. The baseline uses the same values for a fair comparison."""

    max_rounds: int = 3
    max_tasks_per_round: int = 4
    max_tool_calls_per_task: int = 6
    max_total_tool_calls: int = 30
    max_tool_retries: int = 2
    max_task_attempts: int = 2
    max_repair_attempts: int = 2
    parallel_workers: int = 4
    inconclusive_threshold: float = 0.5
    min_supporting_evidence: int = 2
    min_confidence_margin: float = 0.05
    max_contradiction_share: float = 0.35
    max_reported_gaps: int = 10


class Settings(BaseModel):
    llm: LLMSettings = Field(default_factory=LLMSettings)
    investigation: InvestigationSettings = Field(default_factory=InvestigationSettings)


_ENV_VARS = {
    "llm": {
        "provider": "LLM_PROVIDER",
        "model": "LLM_MODEL",
        "api_key": "OPENROUTER_API_KEY",
        "base_url": "LLM_BASE_URL",
        "max_tokens": "LLM_MAX_TOKENS",
        "reasoning_effort": "LLM_REASONING_EFFORT",
        "timeout_s": "LLM_TIMEOUT_S",
        "max_retries": "LLM_MAX_RETRIES",
        "structured_outputs": "LLM_STRUCTURED_OUTPUTS",
    },
    "investigation": {
        "max_rounds": "INV_MAX_ROUNDS",
        "max_tasks_per_round": "INV_MAX_TASKS_PER_ROUND",
        "max_tool_calls_per_task": "INV_MAX_TOOL_CALLS_PER_TASK",
        "max_total_tool_calls": "INV_MAX_TOTAL_TOOL_CALLS",
        "max_tool_retries": "INV_MAX_TOOL_RETRIES",
        "max_task_attempts": "INV_MAX_TASK_ATTEMPTS",
        "max_repair_attempts": "INV_MAX_REPAIR_ATTEMPTS",
        "parallel_workers": "INV_PARALLEL_WORKERS",
        "inconclusive_threshold": "INV_INCONCLUSIVE_THRESHOLD",
        "min_supporting_evidence": "INV_MIN_SUPPORTING_EVIDENCE",
        "min_confidence_margin": "INV_MIN_CONFIDENCE_MARGIN",
        "max_contradiction_share": "INV_MAX_CONTRADICTION_SHARE",
        "max_reported_gaps": "INV_MAX_REPORTED_GAPS",
    },
}


def load_settings(env_file: Path | None = None) -> Settings:
    """Build settings from the environment. Values already in the environment win over .env."""
    load_dotenv(env_file or PROJECT_ROOT / ".env", override=False)
    sections: dict[str, dict[str, str]] = {}
    for section, mapping in _ENV_VARS.items():
        sections[section] = {
            field: os.environ[var].strip()
            for field, var in mapping.items()
            if os.environ.get(var, "").strip()
        }
    llm = sections["llm"]
    if llm.get("reasoning_effort", "").lower() in {"none", "off"}:
        llm["reasoning_effort"] = None
    return Settings(
        llm=LLMSettings(**llm),
        investigation=InvestigationSettings(**sections["investigation"]),
    )
