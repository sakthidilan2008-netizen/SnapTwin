# Causal Model (design — Stage 6/7 not yet implemented)

This document specifies the reasoning contract `backend/causal/` must
implement. It exists now, ahead of the code, so Stage 6/7 has a fixed
target instead of being designed ad hoc mid-implementation.

## Vocabulary

- **H** — a `Hypothesis` (see `backend/models/hypothesis.py`), scoped to one
  `FailureClass`.
- **E** — accumulated `EvidenceRef`s, each with its own `Provenance`.
- **I** — a documented, reversible `Experiment.intervention`.
- **O** — the observed `Experiment.actual_outcome`.

## Belief representation

Each hypothesis carries:

- `prior` — belief before the most recent intervention.
- `confidence` — current belief, conceptually `P(H | E)` before any
  intervention, and `P(H | E, do(I), O)` after one.

Updates must be **transparent, likelihood-ratio-style**, not an opaque
model score. Every change to `confidence` must be accompanied by an
appended, human-readable entry in `Hypothesis.rationale` explaining *why*
— e.g.:

```
Before: H1=0.48, H2=0.31, H3=0.21
Intervention EXP-001: disabled a documented compatibility shim (low risk, reversible)
Outcome: crash signature changed from STATUS_ILLEGAL_INSTRUCTION to clean exit
Update: H1 -> 0.81 (outcome matches expected_if_true), H2 -> 0.12, H3 -> 0.07
Rationale: "Crash signature change under a purely compatibility-layer
intervention strongly discriminates in favor of an architecture/emulation
cause over a graphics- or dependency-only cause, which would not be
expected to react to this specific intervention."
```

## What this system does and does not claim

- It does **not** claim formal causal identification (e.g. backdoor
  criterion satisfaction, do-calculus guarantees) unless the specific
  scenario's assumptions are actually checked and satisfied. Absent that,
  updates are described as "evidence-based belief revision," not "proven
  causation."
- Confidence numbers are **calibrated relative to evidence actually
  collected in this investigation**, not a global learned prior across
  unrelated applications (that's the benchmark's job, Stage 12, and even
  there only as an aggregate evaluation metric, not something fed back into
  a single investigation's numbers without new evidence).

## Minimum viable update rule (Stage 6 starting point)

For the first implementation, use a simple, auditable likelihood-ratio
update rather than a full Bayesian network:

1. Each hypothesis starts with a prior derived from how many *independent*
   pieces of supporting evidence it has versus contradicting evidence,
   normalized across active hypotheses.
2. An experiment's outcome is scored against each hypothesis's
   `expected_if_true` / `expected_if_false` text via structured outcome
   matching (not free-text LLM judgment as the source of truth — LLM
   assistance may *draft* the match, but the structured comparator in
   `experiments/result_comparator.py` decides it).
3. Hypotheses whose expectation matched the outcome get a confidence boost;
   hypotheses whose expectation was contradicted get reduced; unrelated
   hypotheses are left approximately unchanged, and that "unchanged"
   decision is itself logged as a rationale entry (e.g. "H3 not affected by
   this intervention by design — targets a different failure class").
4. Re-normalize so confidences remain interpretable, but never let a single
   experiment alone push a hypothesis above a "root cause" threshold
   without at least one corroborating piece of independently-sourced
   evidence (different `SourceMechanism`).

This rule is intentionally simple and auditable for the research prototype
stage; `docs/RESEARCH.md` notes more rigorous causal-inference approaches as
future work, not something already implemented.
