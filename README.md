# Incident Investigator v2

An LLM-powered multi-agent system that investigates production incidents. It is compared against a
single-agent baseline that uses the same model, tools and limits.

Six agents (orchestrator, observability, dependency, reasoning, critic, reporting) collaborate through
typed messages and a shared evidence ledger. The LLM makes the investigative decisions; Python handles
validation, tool execution, retries, budgets, stop conditions and grading. See
[docs/architecture.md](docs/architecture.md) for the diagram and protocol, and
[docs/technical_note.md](docs/technical_note.md) for the design rationale and limitations.

## Setup

Requires Python 3.11+.

```bash
python -m pip install -e ".[dev]"
cp .env.example .env        # then set OPENROUTER_API_KEY
```

- `OPENROUTER_API_KEY` must be an **inference** key from https://openrouter.ai/settings/keys. A
  management/provisioning key is rejected with `401`.
- Default model: `anthropic/claude-haiku-5.5`. To switch, set `LLM_MODEL=anthropic/claude-sonnet-5.5`
  or pass `--model`.
- All limits (rounds, tool budgets, retries, inconclusive thresholds) are environment variables; see
  `.env.example`.

## Usage

```bash
# offline tests (mocked LLM, no API credits)
python -m pytest

# investigate one scenario
python scripts/run_investigation.py S05
python scripts/run_investigation.py S05 --system baseline

# full comparison: multi-agent vs baseline over all scenarios, then the outcome analysis
python scripts/run_evaluation.py --repeats 3 --out results/final
python scripts/analyze_results.py results/final

# regenerate the synthetic data (deterministic)
python scripts/generate_scenarios.py
```

Every run saves a full JSON record (plan, tasks, findings, each round's hypotheses and critique, event
trace, token usage, tool statistics) and a Markdown report under `results/`.

## Data

There are 12 synthetic scenarios in `data/incidents/` (overview in
[data/incidents/README.md](data/incidents/README.md)). They include misleading deploys and postmortems,
conflicting evidence, cascading failures, injected tool timeouts, partial results and errors, and two
scenarios where the correct answer is "inconclusive". Ground truth lives in `data/ground_truth/` and is
read only by the evaluator.

## Layout

```text
src/incident_investigator/
  config.py  llm_client.py  schemas.py  state.py  engine.py  scenarios.py  render.py
  agents/      orchestrator, observability, dependency, reasoning, critic, reporting (+ base)
  tools/       logs, metrics, deployments, dependencies, historical_incidents (+ base: executor)
  evaluation/  baseline, metrics, runner
  scripts/       run_investigation.py, run_evaluation.py, analyze_results.py, generate_scenarios.py
  tests/         offline tests with a scripted LLM (tests/fakes.py)
  docs/          architecture, technical note, evaluation results
```

## Results

Final evaluation: 72/72 runs, Claude Haiku 5.5. Diagnosis accuracy was 55.6% for the multi-agent system and
83.3% for the single-agent baseline. The leading hypothesis was correct in 90.0% vs 96.7% of runs; the
multi-agent system abstained more often, including correctly on every ambiguous incident. It cost $1.45 vs
$0.23 and took 126 s vs 23 s per run. See [docs/evaluation_results.md](docs/evaluation_results.md) for the full,
measured results and limitations; raw run records are in `results/final/`.
