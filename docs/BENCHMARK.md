# Benchmark (planned — Stage 12 not yet implemented)

## Dataset shape

Each benchmark case (`benchmark/scenarios/`) will provide:

```json
{
  "application": "...",
  "architecture": "...",
  "dependencies": ["..."],
  "failure_class": "F1_architecture_mismatch",
  "ground_truth": "...",
  "baseline_result": { "...": "..." }
}
```

## Metrics (to be computed by `benchmark/metrics.py`)

- Root Cause Top-1 / Top-3 accuracy
- Precision / Recall / F1 against `failure_class`
- False positive rate / false negative rate
- Diagnostic time (wall clock)
- Number of experiments required to reach the accepted root cause
- Remediation success rate
- Verification success rate
- Runtime overhead SnapTwin itself imposes

## Rule

The benchmark runner must produce these numbers by actually executing
scenarios end-to-end. No numbers should appear in this document, the
README, or any report until they come from a real run of
`benchmark/runner.py` against held-out scenarios — this file intentionally
contains no example numbers to avoid them being mistaken for real results
later.

## Status

Not yet implemented.
