# Architecture

## Layering

```
collectors/ + analyzers/   -->  raw, provenance-tagged facts
        |
        v
     twin/                 -->  ExecutionTwin graph (nodes/edges over those facts)
        |
        v
     causal/                -->  Hypothesis set + belief updates over the twin + telemetry
        |
        v
   experiments/             -->  Safe interventions that discriminate between hypotheses
        |
        v
  remediation/               -->  Recommendation + mandatory re-run verification
        |
        v
     api/  -->  frontend/    -->  investigation UI + final report
```

`ai/` is a cross-cutting layer consumed by `causal/` and `remediation/` for
hypothesis generation assistance, evidence summarization, and natural
language narration — it never replaces the structured engine's actual
belief updates (see `docs/CAUSAL_MODEL.md`).

## Why models/ is split the way it is

- `common.py` — shared `Provenance`/`EvidenceType`/`Architecture` vocabulary
  every other model reuses. This is what makes "every important result has
  source/timestamp/confidence/evidence_type" enforceable instead of aspirational.
- `application.py` — static identity of the target binary (Phase 2 output).
- `dependency.py` — per-DLL facts (Phase 2/3 output); separate from `twin/`
  because this is *data about* dependencies, not the graph structure itself.
- `execution.py` — one record per actual run of the app (baseline,
  experiment, verification). This is what `result_comparator.py` diffs.
- `telemetry.py` — host/OS-level snapshots and log/WER entries; can exist
  without ever running the target app.
- `hypothesis.py` — Phase 6/7 candidate explanations, scoped to the
  `FailureClass` taxonomy in `config/failure_taxonomy.yaml`.
- `experiment.py` — Phase 8 controlled interventions; the type shape itself
  enforces "risk + rollback + both expected outcomes before running."
- `remediation.py` — Phase 11/12 recommendation + the verification record
  that must come from an actual re-run, not a model's opinion.
- `report.py` — final aggregate artifact tying one investigation together.

## Current implementation status

Only `backend/models/*` and `backend/collectors/system_collector.py` are
implemented and tested as of Stage 1. Every other package listed in the
tree below exists as an empty, importable package (`__init__.py` only) so
later stages have a stable place to land without restructuring the repo.

```
backend/
  models/         [Stage 1 — implemented]
  collectors/     [Stage 1 partial — system_collector.py implemented;
                   process/eventlog/wer/etw/runtime collectors pending Stage 4]
  analyzers/      [pending Stage 2/3]
  twin/           [pending Stage 5]
  causal/         [pending Stage 6]
  experiments/    [pending Stage 7]
  remediation/    [pending Stage 8]
  ai/             [pending Stage 9]
  api/            [pending — wired in once there's enough to serve]
```
