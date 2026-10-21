# Evaluation results

**Final evaluation, completed 2026-10-21:** 12 scenarios × 2 systems × 3 repeats = **72 of 72 runs completed,
0 errors**. Model `anthropic/claude-haiku-5.5` via OpenRouter (reasoning effort `low`), dataset v2.1. Every
number below is measured from the saved run records in `results/final/`, except the clearly labelled
re-scoring in the sensitivity section.

## Headline comparison

| Metric | Multi-agent | Single-agent baseline |
|---|---|---|
| **Diagnosis accuracy** (all 36 runs) | **55.6%** (20/36) | **83.3%** (30/36) |
| Accuracy, scenarios with a determinable cause (30 runs) | 46.7% (14/30) | 90.0% (27/30) |
| Accuracy, scenarios that should be inconclusive (6 runs) | **100%** (6/6) | 50.0% (3/6) |
| Leading hypothesis correct, ignoring the conclusion (30 runs) | 90.0% (27/30) | 96.7% (29/30) |
| Correct cause in top 3 | 90.0% | 96.7% |
| Conclusive outcomes | 15/36 (41.7%) | 31/36 (86.1%) |
| Inconclusive outcomes | 21/36 (58.3%) | 5/36 (13.9%) |
| Precision when conclusive (determinable scenarios) | 93.3% (14/15) | 96.4% (27/28) |
| Conclusive on a planted decoy | 0 | 0 |
| Citation validity (cited ids that exist in the ledger) | 99.8% (10,989 valid, 22 invalid) | 97.4% (1,822 valid, 50 invalid) |
| Key evidence cited in the report | 96.2% | 90.6% |
| Tool calls per run (total) | 29.8 (1,072) | 9.4 (338) |
| Runs that used the whole 30-call tool budget | 32/36 | 0/36 |
| LLM calls per run (total) | 29.3 (1,053) | 3.9 (139) |
| Invalid agent outputs (repair attempts), total | 11 | 0 |
| Prompt tokens per run | 235,264 | 41,332 |
| Completion tokens per run | 33,604 | 4,373 |
| Total tokens (all runs) | 9,679,233 | 1,645,384 |
| **Cost, provider-reported (all runs)** | **$1.452** | **$0.228** |
| Mean / median latency per run | 126 s / 127 s | 23 s / 22 s |
| Errored runs, runs without usage data | 0, 0 | 0, 0 |

Total measured cost of the evaluation was $1.68. Raw records: `results/final/runs/` (72 JSON and 72 Markdown),
`rows.json`, `summary.json`, `summary.md`, `analysis.md` / `analysis.json` (from `scripts/analyze_results.py`)
and the run log `eval.log`.

## Outcome breakdown (runs)

| Outcome | Multi-agent | Baseline |
|---|---|---|
| Correct diagnosis (conclusive, right cause) | 14 | 27 |
| **Abstained although the leading hypothesis was right** | **13** | 2 |
| Abstained with a wrong leading hypothesis | 2 | 0 |
| Wrong diagnosis (conclusive, wrong cause) | 1 | 1 |
| Correct abstention (ground truth inconclusive) | 6 | 3 |
| Unwarranted conclusion (ground truth inconclusive) | 0 | 3 |

Per scenario (correct / leading hypothesis correct / conclusive, out of 3):

| | S01 | S02 | S03 | S04 | S05 | S06 | S07 | S08 | S09 | S10* | S11 | S12* |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Multi-agent | 0/3/0 | 2/3/2 | 1/3/1 | 1/1/2 | 3/3/3 | 1/3/1 | 2/3/2 | 0/3/0 | 1/2/1 | 3/–/0 | 3/3/3 | 3/–/0 |
| Baseline | 3/3/3 | 3/3/3 | 3/3/3 | 3/3/3 | 3/3/3 | 2/2/3 | 3/3/3 | 1/3/1 | 3/3/3 | 3/–/0 | 3/3/3 | 0/–/3 |

\* S10 and S12 have no determinable cause; the only correct outcome is inconclusive.

## Key findings

1. **The baseline is more accurate overall: 83.3% vs 55.6%.** Measured on this benchmark, the multi-agent
   system does not justify its cost: it uses about 6.4× the cost, 5.9× the tokens and 5.5× the latency.
2. **Diagnosis is not the difference; abstention is.** Both systems usually find the right cause: the leading
   hypothesis is correct in 90.0% (multi-agent) and 96.7% (baseline) of determinable runs. 13 of the
   multi-agent's 16 wrong outcomes on determinable scenarios are abstentions with the right leading hypothesis.
3. **The multi-agent system is better calibrated on genuinely ambiguous incidents.** It abstained correctly in
   all 6 runs of S10 and S12. The baseline named a cause for S12 (two simultaneous changes, gateway logs
   inaccessible) in all 3 runs at confidence 0.60. The same decision criteria accepted that, because the
   baseline has no critic to raise contradictions.
4. **Neither system fell for a planted decoy** (misleading deploys, postmortems or dependency health).
   Wrong leading hypotheses were rare: multi-agent S04 (blamed payment-service instead of the external
   provider, 2 runs) and S09 r2; baseline S06 r1 (right component, wrong category).
5. **Grounding is strong for both systems.** The multi-agent system cites far more evidence with fewer
   invalid ids (99.8% vs 97.4% validity) and cites more of the key evidence (96.2% vs 90.6%).

## Why the multi-agent system abstained

Of the 21 multi-agent inconclusive runs, 20 failed the contradiction-share criterion (contradicting evidence
> 35% of the evidence weighed), 10 the confidence criterion (< 0.50) and 2 the verified-support criterion
(several runs failed more than one). Almost all contradiction weight came from **evidence-backed material
critic objections**, so the cause is the critic together with how its objections are counted. The
objections fall into three groups:

- **Remaining synthetic-data inconsistencies (S01 ×3, S03 r1).** The critic was factually right about the
  data. In S01, the gateway's 5xx rate (6.2% of 420 req/s) exceeds what checkout's failures (18.5% of 85 req/s)
  can produce. Independent timing jitter per log stream lets a gateway 500 appear before checkout's first NPE.
  Logs are sparse samples (about 40 error lines in 30 min against hundreds of failures per minute). In S03, the
  worker logs 92% GC overhead while throughput stays normal. These are generator defects, not real ambiguity.
- **Unverifiable mechanism assumptions (S02 r3, S06 r3, S08, S09 r1).** The critic objected that a mechanism
  link (for example "this flag gates this code path", or "these 503s really come from the provider") has no
  direct evidence. No available tool can provide such evidence, so these objections should have been minor.
- **Weak alternatives (S06 r2, S07 r1).** For example, inventory latency rising under a traffic surge was
  offered as an alternative cause.

The baseline's 5 abstentions: S10 ×3 (correct; low confidence) and S08 ×2 (its own contradicting evidence
exceeded 35% when payment-service logs were unavailable).

## Design issue found during analysis (not changed)

`decide_conclusion` adds the evidence ids cited by an `alternative_not_ruled_out` objection to the
*contradicting* evidence. Those ids are often evidence that is consistent with both hypotheses (such as the
change record or the onset step) rather than evidence against the leader, so contradiction is over-counted.
This was found after the run. Per the evaluation rules, it was not fixed, and the official numbers above use
the logic as frozen.

## Sensitivity re-scoring (counterfactual, not the official result)

The same saved multi-agent hypotheses and critiques, re-scored with alternative decision rules (no new LLM
calls). The official rule reproduces 20/36 exactly.

| Decision rule applied to the saved multi-agent runs | Correct |
|---|---|
| Official (as evaluated) | 20/36 (55.6%) |
| Ids cited by `alternative_not_ruled_out` objections not counted as contradicting | 25/36 (69.4%) |
| Critic objections ignored (the baseline's situation) | 28/36 (77.8%) |
| *Baseline, official* | *30/36 (83.3%)* |

Even with critic objections ignored entirely, the multi-agent system does not exceed the baseline on this
dataset. Its advantage is limited to the inconclusive scenarios.

## Dataset version and corrections

The evaluation uses dataset **v2.1**, frozen by `data/MANIFEST.json` (SHA-256 of all 84 generated files) and
the git tag `dataset-v2.1`. `tests/test_dataset.py` checks that the committed files match the manifest, that
regenerating reproduces them byte for byte, and that the ground-truth answers are unchanged.

Two corrections were made to v2.0 before the evaluation, after a pre-evaluation S05 run showed evidence that
contradicted itself. The investigating critic had correctly flagged both as unexplained:

1. **Background logs did not follow traffic (all scenarios).** Background log lines were generated at a
   constant rate, so a service whose request rate collapsed still logged normal successful operations. Now
   background volume scales with the service's request-rate curve, and routine success (INFO) lines thin out
   in proportion to its error rate. As part of this, auth-service's baseline request rate was set to the share
   of caller traffic that needs a live token check (80 req/s, not 300). S12's auth surge was scaled to match
   (+31%, as before).
2. **S05 checkout TLS message.** Checkout logged `remote error: tls: handshake failure`, which is a
   server-sent alert and does not fit an expired *server* certificate. It now logs the client-side
   validation failure (`SSLHandshakeException: PKIX path validation failed ... validity check failed (peer
   auth.internal:8443)`). The message still blames the peer rather than checkout, it does not say "expired"
   (only the gateway's x509 message does), and the misleading checkout deploy is unchanged.

Ground-truth answers, key-evidence groups and decoys are unchanged in every scenario. Evidence ids shifted,
because the noise was regenerated; ground truth is regenerated with them. The inconsistencies listed under
"Why the multi-agent system abstained" remain in v2.1.

## Limitations

- **Small, synthetic benchmark.** 12 scenarios with one shared topology, 3 repeats and one model. The
  scenarios were written by the same authors as the prompts. Differences of a few runs are within noise.
- **Remaining data inconsistencies** (above) penalise the system that scrutinises evidence hardest, which here
  is the multi-agent system.
- **Asymmetric scrutiny.** Only the multi-agent system has a critic whose objections feed the conclusion
  rule. The baseline is judged by the same rule on its own self-reported contradictions. This explains both
  the multi-agent's over-abstention and the baseline's unwarranted conclusions on S12.
- **Decision rule.** Thresholds (confidence 0.50, contradiction share 35%, margin 0.05) are heuristics, and
  LLM confidences are uncalibrated. The over-counting issue above inflates multi-agent abstention.
- **Budget saturation.** The multi-agent system used the whole tool budget in 32/36 runs, so its results
  depend on that budget.
- **Grading** checks component and category only, not the quality of explanations or remediation.

## How to reproduce

```bash
python scripts/run_evaluation.py --repeats 3 --out results/final
python scripts/analyze_results.py results/final
```

## Metric definitions

| Metric | Definition |
|---|---|
| Diagnosis accuracy | Conclusive with the correct top component and category, or inconclusive when the ground truth is inconclusive |
| Leading hypothesis correct | Top-ranked hypothesis matches the ground truth, regardless of conclusive/inconclusive status |
| Top-3 recall | Correct cause anywhere in the top 3 hypotheses (determinable scenarios only) |
| Conclusive on a decoy | Conclusive with a top hypothesis equal to a planted decoy |
| Citation validity | Cited ids that exist in the evidence ledger, divided by all cited ids (invalid ids are removed before the report) |
| Key evidence cited / retrieved | Share of ground-truth key-evidence groups cited in the report / retrieved by any tool |
| Tool calls, LLM calls | Counted by the executor and the usage meter |
| Tokens, cost | Provider-reported `usage` per call; `n/a` when not reported (no run lacked it) |
| Latency | Wall-clock time per investigation, sequential runs |
