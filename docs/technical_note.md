# Technical note

**Problem.** Incident investigation means gathering evidence across systems while resisting plausible but
wrong explanations. We tested whether collaborating LLM agents beat one agent with the same model and tools.

**Design.** Six roles exchange typed Pydantic messages through shared state:
- The orchestrator plans a task graph.
- Observability and dependency specialists run their own tool loops in parallel.
- The reasoning agent ranks competing hypotheses with supporting and contradicting evidence.
- The critic grades objections (material or minor), cites evidence and requests follow-ups.
- The reporting agent separates facts, assumptions and inferences.

The LLM makes every investigative judgement. Python handles validation, budgets, bounded retries, fault
injection, citation checks and stopping. The conclusion is computed deterministically from the leader's
confidence, verified support, margin and share of contradicting evidence. Critic objections count only if
they are material and evidence-backed.

**Grounding and data.** Every tool record has an id; citations of ids that were never retrieved are stripped
and counted. Twelve seeded synthetic scenarios include decoy deploys and postmortems, conflicting health
checks, cascades, tool failures and two genuinely ambiguous incidents. The dataset is frozen by hashes.

**Evaluation** (Claude Haiku 5.5, 72 runs, all measured):
- Diagnosis accuracy was 55.6% for the multi-agent system against 83.3% for the baseline.
- The leading hypothesis was correct in 90.0% and 96.7% of determinable runs; neither system was ever
  conclusive on a decoy.
- The multi-agent system abstained in 13 runs despite a correct leader, but abstained correctly on all six
  ambiguous runs; the baseline did so in three of six.
- Citation validity was 99.8% against 97.4%.
- The multi-agent system cost $1.45 against $0.23, with 6× the tokens and 126 s against 23 s per run.

On this benchmark the multi-agent design does not justify its cost. The critic improves calibration on
ambiguous incidents but causes over-abstention elsewhere.

**Why.** Twenty of 21 multi-agent abstentions exceeded the contradiction-share limit through evidence-backed
critic objections. Some correctly flagged remaining data defects: in S01, gateway errors exceed checkout's,
log timing jitter breaks causal order, and error logs are sparse. Others objected to mechanism links no tool
can verify. Post-run analysis also found that evidence cited for "alternative not ruled out" objections is
counted as contradicting, although it often fits both hypotheses. Counterfactual re-scoring of the saved
runs gives 25/36 without that rule and 28/36 ignoring the critic, both still below the baseline.

**Limitations.**
- Small synthetic benchmark: 12 scenarios, one topology, one model, three repeats, same authors for
  scenarios and prompts.
- Remaining data defects penalise the most sceptical system.
- Only the multi-agent system has a critic feeding the conclusion rule.
- Thresholds are heuristic, and LLM confidences are uncalibrated.
- The tool budget was exhausted in 32 of 36 multi-agent runs.
- Grading ignores explanation quality.

**Next steps.**
- Fix the generator's error-volume, timing and log-sampling consistency.
- Treat shared evidence as neutral.
- Make unverifiable-mechanism objections minor.
- Rerun on a larger, independently written scenario set.
