# Evaluation results

**Status: no live evaluation has been run yet.** The configured OpenRouter key is a management
(provisioning) key, which OpenRouter rejects for model calls (`401 User not found`). No accuracy, token or
latency numbers are reported here until a real run produces them.

## Dataset version and corrections

The evaluation uses dataset **v2.1**, frozen by `data/MANIFEST.json` (SHA-256 of all 84 generated files).
`tests/test_dataset.py` checks that the committed files match the manifest, that regenerating reproduces them
byte for byte, and that the ground-truth answers are unchanged.

Two corrections were made to v2.0 after a pre-evaluation S05 run showed evidence that contradicted itself.
The investigating critic correctly flagged both as unexplained:

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
because the noise was regenerated; ground truth is regenerated with them.

## How to produce the results

```bash
python scripts/run_evaluation.py --repeats 3 --out results/final
```

The command writes:

- `results/final/summary.md`: the comparison table (copy it below);
- `results/final/summary.json` and `rows.json`: machine-readable metrics;
- `results/final/runs/`: each run's full record (plan, tasks, findings, every round's hypotheses and
  critique, trace, usage) and its Markdown report.

## Metrics

| Metric | Definition |
|---|---|
| Diagnosis accuracy | Conclusive with the correct top component and category, or inconclusive when the ground truth is inconclusive |
| Top-3 recall | Correct cause anywhere in the top 3 hypotheses (determinable scenarios only) |
| Misled rate | Conclusive on a planted decoy hypothesis |
| False-inconclusive rate | Abstained although the cause was determinable |
| Citation validity | Cited ids that exist in the evidence ledger, divided by all cited ids |
| Key evidence cited / retrieved | Share of ground-truth key-evidence groups cited in the report / retrieved by any tool |
| Tool calls, LLM calls | Counted by the executor and the usage meter |
| Tokens, cost | Provider-reported `usage`; `n/a` when not reported |
| Latency | Wall-clock time per investigation |

## Results

_To be filled from `results/final/summary.md` after the first live run._
