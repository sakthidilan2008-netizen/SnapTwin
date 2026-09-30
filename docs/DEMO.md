# Demo (planned — Stage 11 not yet implemented)

## Goal

A reproducible, deterministic scenario that does not depend entirely on an
arbitrary third-party application, so the demo works the same way every
time it's run.

## Planned approach

A small controlled demo application (`demo/demo_app/`) will be built with a
deliberate, documented architecture/dependency issue (e.g. an x64-only
dependency loaded on an ARM64 host through the emulation path), so the
failure is legitimate and reproducible rather than scripted fiction.

## Mandatory labeling rule

Every artifact produced by the demo scenario — execution records,
experiments, hypotheses that reference demo evidence — must be tagged at
the model level:

- `ExecutionRecord.is_demo_data = true`
- `Experiment.is_demo_scenario = true`
- `InvestigationReport.contains_demo_data = true`

The frontend (Stage 10, not yet implemented) must render a persistent,
unmissable visual indicator whenever any of these flags is true, so
controlled demonstration data is never confused with real system evidence.

## Status

Not yet implemented. This document exists ahead of the code so Stage 11 has
a fixed contract to build against, consistent with how `docs/CAUSAL_MODEL.md`
precedes Stage 6/7.
