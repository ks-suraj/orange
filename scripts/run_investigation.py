"""Investigate one scenario with the multi-agent system or the baseline.

    python scripts/run_investigation.py S05
    python scripts/run_investigation.py S05 --system baseline --model anthropic/claude-sonnet-5.5
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from incident_investigator.config import RESULTS_DIR, load_settings
from incident_investigator.evaluation.runner import SYSTEMS
from incident_investigator.llm_client import build_client
from incident_investigator.render import report_to_markdown
from incident_investigator.scenarios import load_scenario, scenario_ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenario", choices=scenario_ids())
    parser.add_argument("--system", choices=list(SYSTEMS), default="multi_agent")
    parser.add_argument("--model", help="override LLM_MODEL")
    args = parser.parse_args()

    settings = load_settings()
    if args.model:
        settings.llm.model = args.model
    client = build_client(settings.llm)
    result = SYSTEMS[args.system](client, settings).investigate(load_scenario(args.scenario))

    print(report_to_markdown(result.report))
    u, t = result.usage, result.tool_stats
    print(f"--- latency {result.latency_s:.1f}s | LLM calls {u['llm_calls']} | tokens prompt={u['prompt_tokens']} "
          f"completion={u['completion_tokens']} | cost ${u['cost_usd']} | tool calls {t['tool_calls']} "
          f"(failed {t['failed_calls']}, partial {t['partial_calls']}) | citations {result.citations}")

    out = RESULTS_DIR / "single_runs"
    out.mkdir(parents=True, exist_ok=True)
    stem = out / f"{args.scenario}_{args.system}_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    stem.with_suffix(".json").write_text(json.dumps(result.to_dict(), indent=2, default=str), encoding="utf-8")
    stem.with_suffix(".md").write_text(report_to_markdown(result.report), encoding="utf-8")
    print(f"--- saved {stem}.json / .md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
