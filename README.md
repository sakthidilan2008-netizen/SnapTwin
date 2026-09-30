# SnapTwin — Causal Execution Twin for Snapdragon Windows PCs

> **Status: Stage 2 of 12 implemented.** Repository scaffold, core data
> models, real system discovery (`SystemCollector`), and PE binary analysis
> (`PEAnalyzer`) are done and tested.
> Everything else described below is the design this prototype is being
> built toward — see the per-phase checklist at the bottom for what exists
> today versus what's planned.

## What is SnapTwin?

SnapTwin is a research prototype for **diagnosing why an application fails
or degrades on a Snapdragon (Windows-on-ARM) PC**, using an explicit,
evidence-driven investigation loop instead of a single AI guess:

```
OBSERVE → HYPOTHESIZE → INTERVENE → EXECUTE → MEASURE → LOCALIZE → REMEDIATE → VERIFY → LEARN
```

The guiding line for the project: **we don't ask an AI what's wrong — we
make the PC prove it.** Every claim SnapTwin makes is tagged as either
`observed` (came directly from a Windows mechanism) or `inferred` (derived),
and root-cause claims are only accepted after a controlled, reversible
experiment discriminates between competing explanations.

SnapTwin is **not** a chatbot, a compatibility checker, a benchmark
dashboard, an NPU demo, a simple ARM64 detector, or a generic RAG app.

## What it can actually observe (today / planned)

| Signal | Mechanism | Status |
|---|---|---|
| OS name/version/architecture | `platform` module | ✅ Stage 1 |
| CPU architecture, core counts | `platform` + `psutil` | ✅ Stage 1 |
| Snapdragon/Qualcomm CPU hint | CPU model string pattern match | ✅ Stage 1 (hint only, not a confirmed capability claim) |
| System memory | `psutil` | ✅ Stage 1 |
| GPU adapter details | WMI `Win32_VideoController` | ⏳ Windows-only, implemented but untestable on this dev host |
| NPU presence/provider | Windows AI execution-provider APIs | ⏳ Planned (Phase 10), explicitly stubbed as `unavailable` until real evidence exists |
| PE architecture / imports / manifest | `pefile` | ✅ Stage 2 |
| Dependency resolution & DLL architecture | Static + runtime module enumeration | ⏳ Stage 3 |
| Windows Event Log, WER | `pywin32` / Windows APIs | ⏳ Stage 4 |
| ETW | Windows ETW APIs | ⏳ Stage 4 (optional collector, interface defined, real backend later) |

## What it infers (and always labels as such)

Anything derived rather than read directly — e.g. "this dependency chain is
*likely* the failure point" — carries `evidence_type: inferred` and a
`confidence` grounded in the causal engine's explicit belief updates, never
an unexplained score.

## What it cannot observe

SnapTwin does not have undocumented access to Microsoft's Prism emulator
internals. It does not claim instruction-level Prism tracing, kernel
introspection, arbitrary driver repair, or perfect compatibility
prediction. Where a mechanism is genuinely unavailable (e.g. GPU/NPU
detail on a non-Windows development host), SnapTwin reports
`platform_unavailable` rather than fabricating a plausible-looking value —
this is enforced in code, not just policy (see
`backend/collectors/system_collector.py` and its tests).

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full module
layout. At a glance:

```
backend/
  models/        Pydantic data contracts (application, dependency, execution,
                 telemetry, hypothesis, experiment, remediation, report)
  analyzers/     Static analysis (PE, architecture, dependencies, drivers, ...)
  collectors/    Runtime evidence gathering (system, process, event log, ...)
  twin/          Execution twin graph construction
  causal/        Hypothesis generation + belief updates
  experiments/   Safe, reversible intervention engine
  remediation/   Recommendation + verification
  ai/            Anomaly detection, hypothesis ranking, LLM-assisted narration
  api/           FastAPI routes
frontend/        React/TypeScript investigation dashboard
demo/            Deterministic, clearly-labeled demo scenarios
benchmark/       Ground-truth scenario dataset + scoring
tests/           Unit + adversarial test suite
```

## Installation

```bash
pip install -r requirements.txt
# Windows-only extras (pefile, pywin32) install automatically on win32
```

## Running the tests (Stage 2)

```bash
python -m pytest tests/ -v
```

## Usage (Stage 2)

```python
from collectors.system_collector import SystemCollector

snapshot = SystemCollector().collect()
print(snapshot.model_dump_json(indent=2))
```

On a real Snapdragon Windows PC this returns genuine ARM64/CPU/GPU/memory
facts. On any other host (including this Linux development container) it
returns genuine OS/CPU/memory facts and *honestly* reports GPU/NPU detail
as unavailable — it never fakes them.

## Scientific methodology

See [`docs/CAUSAL_MODEL.md`](docs/CAUSAL_MODEL.md) for how hypotheses,
evidence, interventions, and outcomes relate, and
[`docs/RESEARCH.md`](docs/RESEARCH.md) for the research framing. SnapTwin
uses transparent, explainable likelihood-style belief updates; it does not
claim formal causal identification (e.g. do-calculus guarantees) unless the
underlying assumptions are actually satisfied for a given scenario.

## Limitations

See [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md). In short: this is a
research prototype, most phases beyond Stage 1 are not yet implemented, and
any demo/simulated data is always explicitly labeled as such and never
presented as live OS evidence.

## Phase status

- [x] Stage 1 — repository scaffold, models, `SystemCollector`
- [x] Stage 2 — PE analysis
- [ ] Stage 3 — dependency graph
- [ ] Stage 4 — runtime telemetry
- [ ] Stage 5 — execution twin
- [ ] Stage 6 — causal engine
- [ ] Stage 7 — experiment engine
- [ ] Stage 8 — remediation + verification
- [ ] Stage 9 — AI components
- [ ] Stage 10 — frontend
- [ ] Stage 11 — demo mode
- [ ] Stage 12 — benchmark

## License

MIT — see [`LICENSE`](LICENSE).
