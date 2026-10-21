"""Run the multi-agent system and the single-agent baseline over the scenario set.

    python scripts/run_evaluation.py                       # all scenarios, both systems, 1 repeat
    python scripts/run_evaluation.py --scenarios S01 S05 --repeats 3
    python scripts/run_evaluation.py --model anthropic/claude-sonnet-5.5 --out results/sonnet
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from incident_investigator.config import RESULTS_DIR, load_settings
from incident_investigator.evaluation.runner import SYSTEMS, run_evaluation
from incident_investigator.llm_client import build_client
from incident_investigator.scenarios import scenario_ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenarios", nargs="*", default=None, help="default: all")
    parser.add_argument("--systems", nargs="*", default=list(SYSTEMS), choices=list(SYSTEMS))
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--model", help="override LLM_MODEL")
    parser.add_argument("--out", type=Path, help="output directory (default: results/<timestamp>)")
    args = parser.parse_args()

    settings = load_settings()
    if args.model:
        settings.llm.model = args.model
    out = args.out or RESULTS_DIR / f"eval_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    summary = run_evaluation(systems=args.systems, scenario_ids=args.scenarios or scenario_ids(), repeats=args.repeats,
                             client=build_client(settings.llm), settings=settings, out_dir=out)
    print(json.dumps(summary["systems"], indent=2))
    print(f"Results written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
