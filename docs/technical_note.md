# Technical note

**Problem.** Investigating a production incident means gathering evidence from several systems, building
competing explanations, and resisting plausible but wrong ones: a deploy that merely coincides with the
onset, the service with the loudest errors, a similar past incident. We test whether splitting this work
across collaborating LLM agents beats a single agent that uses the same model and tools.

**Design.** Six roles exchange typed Pydantic messages through a shared state. The orchestrator plans a
task graph. Observability and dependency specialists run their own tool-use loops in parallel over
disjoint tool sets. The reasoning agent ranks competing hypotheses, each with supporting and
contradicting evidence. The critic checks those hypotheses against the raw evidence ledger and can request
targeted follow-up tasks, which the orchestrator accepts, sharpens or rejects. The reporting agent
separates observed facts, assumptions and inferences. The model makes every investigative judgement;
Python handles everything that should be deterministic. That includes argument validation, tool budgets,
bounded retries, injected faults, the rule that a citation must point at an id actually retrieved, stop
conditions, and the conclusive/inconclusive decision. That decision is computed from the leading
hypothesis's confidence, its verified support, its margin over the runner-up and the share of
contradicting evidence. The critic's objections count only when they are material and cite ledger
evidence; the reporting agent explains the decision but cannot change it.

**Grounding.** Every tool record carries an id and is entered in the evidence ledger. Citations of ids
that were never retrieved are removed and counted. That count gives an objective grounding metric and
stops a hallucinated "fact" from reaching the report as an observation.

**Data.** Twelve seeded synthetic scenarios share one service topology, with about 300 log lines and 46
metric series each. They include misleading deploys, misleading postmortems, conflicting health checks, a
cascading external outage, tool timeouts, partial results, transient and permanent errors, and two
scenarios where the correct answer is "inconclusive". Ground truth is stored separately, and no
incident-specific logic exists in agent code.

**Baseline and fairness.** The baseline is one agent with all five tools, the same model, total tool
budget, fault injection, output schema, citation check and conclusion policy. Grading is deterministic and
uses no LLM judge. Token counts and cost come only from provider-reported usage; missing values are left
empty, never estimated.

**Limitations.**
- The data is synthetic and uses a single topology. Signals are cleaner than real telemetry, and the
  scenarios were written by the same people who wrote the prompts, which risks overfitting.
- Twelve scenarios at a few repeats cannot show small differences with statistical significance;
  results should be read as indicative.
- LLM confidences are not calibrated, so the inconclusive thresholds are heuristics.
- Grading matches components and categories; it does not judge the quality of the explanation or the
  remediation.
- Simulated tool latency is not slept; wall-clock latency is LLM-dominated.
- The multi-agent system makes several times more LLM calls than the baseline; its value has to be
  weighed against that measured cost.
