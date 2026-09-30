# Limitations

This document is not boilerplate — it's load-bearing for how SnapTwin is
allowed to present its own output.

## What SnapTwin does not have

- **No undocumented access to Prism emulator internals.** No instruction-level
  emulation tracing, no kernel introspection, no ability to inspect Prism's
  translation decisions beyond what Windows exposes through supported,
  observable mechanisms (Event Log, WER, process/module enumeration, ETW
  where practically accessible).
- **No arbitrary kernel-driver repair.** Driver-related remediation is
  limited to recommending documented update/reinstall actions, never
  silent modification.
- **No complete "digital twin" of Windows.** `ExecutionTwin` is a graph of
  *evidence SnapTwin actually gathered*, not a simulation of the OS.
- **No perfect compatibility prediction.** Hypotheses carry calibrated
  confidence, not certainty, and are only elevated to a root-cause claim
  after a discriminating experiment.

## Platform limitations of this specific codebase (Stage 1)

- `SystemCollector` was developed and tested primarily in a Linux
  container. GPU (`WMI Win32_VideoController`) and NPU (Windows AI
  execution-provider) collection paths are implemented but can only be
  exercised for real on Windows — on other platforms they correctly report
  `None`/`unavailable` rather than being skipped silently, and this is
  covered by `tests/test_system_collector.py`.
- Snapdragon/Qualcomm CPU detection is a **string pattern match** against
  the CPU model string where the OS exposes one. It is a hint used to route
  further, real NPU-provider checks in a later stage — it is never treated
  as proof that an NPU is present or usable.

## Demo/simulated data

Any data produced by the deterministic demo scenarios (Stage 11, not yet
implemented) will be tagged `evidence_type: simulated` and
`is_demo_data: true` at the model level (see `ExecutionRecord.is_demo_data`,
`Experiment.is_demo_scenario`, `InvestigationReport.contains_demo_data`).
The UI layer must surface these flags; simulated data must never be
presented as live OS evidence.

## Benchmark numbers

No benchmark numbers exist yet (Stage 12 not implemented). When the
benchmark runner is built, its output must come from actually executing
scenarios — this document will be updated with real numbers only, never
placeholder/illustrative figures presented as measured results.

## Research framing

Where this document or `docs/RESEARCH.md` describes something as novel, it
is phrased as a "potential research contribution" or "research gap
hypothesis," not as an independently verified claim of priority.
