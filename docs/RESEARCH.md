# Research Framing

## Why this might exist as a research direction

Windows-on-ARM compatibility diagnosis today is typically either manual
(a developer reading Event Viewer and dependency walkers by hand) or
opaque (an AI assistant offering a plausible-sounding guess with no
evidence trail). SnapTwin's potential research contribution is combining:

1. Structured, provenance-tagged evidence collection from observable OS
   mechanisms, and
2. An explicit, auditable hypothesis-update loop gated by controlled,
   reversible experiments,

into one investigation workflow, specifically for the ARM64/ARM64EC/x64
emulation boundary on Snapdragon Windows devices.

This is framed as a **research gap hypothesis** — that existing
compatibility tooling either skips the causal-experiment step entirely or
does it manually — not as a claim that no prior work exists in adjacent
areas (root-cause analysis systems, causal ML for systems diagnosis, and
crash-triage tooling all have substantial prior art that a literature
review would need to properly situate this against).

## Related areas to survey (not yet done)

- Automated root-cause analysis in distributed systems observability
- Causal inference for software fault localization
- Windows compatibility/shim research (e.g. existing Application
  Compatibility Toolkit literature)
- ARM64EC/emulation-boundary specific tooling, if any exists publicly

## Non-claims

SnapTwin does not claim to be the first system to do causal or
evidence-based failure diagnosis in any general sense. Any statement of
novelty in this project is scoped specifically to the combination described
above, applied to the Windows-on-ARM emulation boundary, and should be
treated as provisional pending a proper literature review.
