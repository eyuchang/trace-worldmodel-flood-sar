# WF-DFLD-01-REFERENCE protocol amendment v1

## Document control

| Field | Value |
|---|---|
| Amendment ID | `reference-protocol-amendment-v1` |
| Decision set | `reference-scientific-decisions-v1` |
| Status | Approved implementation basis; development only |
| Approval date | 2026-08-11 |
| Approved by | Jay Roy, project owner |
| Amends | `reference-protocol-draft-v1` |
| Draft SHA-256 | `03c407ceb1b87041e36f0c58c352840e94bab6cec73a1f69eacd80173e77a552` |
| Recommendation SHA-256 | `015368939139cd513241ce55d1716ae66f49dd0ee312ab78baf3b7c51759b222` |
| Implementation base | `f89cf16fabae7578bad60bf86060c1536e253c9c` |
| Confirmatory authorization | None |
| LEAP authorization | None |

Jay approved all eight recommendations in
`WF_DFLD_01_REFERENCE_DECISION_RECOMMENDATIONS.md`. This amendment records the
approved scientific basis inside the repository before affected implementation
or coefficient fitting. It is not a preregistration for a confirmatory study and
does not authorize validation, holdout derivation, or LEAP behavior.

Where this amendment conflicts with the draft ambiguity ledger, this amendment
controls. All other draft requirements remain in force until a later versioned
amendment explicitly changes them.

## Approved decisions

### D1 — Physical evidence and calibration language

Reference uses a transparent reduced-order synthetic physical model with units,
component provenance, source-supported ranges, and declared historical
landmarks. It is a systems-integration scenario, not a historical
reconstruction, hydrodynamic forecast, field validation, or causal estimate of
the 1972, 1980, 1997, 2004, or 2022–23 events. Any later predictive-validity
claim requires an independent observational dataset and a separately frozen
validation protocol.

### D2 — Timeline and report-process estimands

The burn-in is the half-open interval `[-48 h, 0)`. The primary evaluation is
`[0, 96 h)`, with censoring at exactly `T+96 h`. Burn-in state, costs,
commitments, and fatigue carry into evaluation.

Approximately 2,900 is the expected number of controller-visible public reports
during the 96-hour evaluation only. Burn-in reports are separate. The 95/hour
quantity is the nonhomogeneous-Poisson intensity throughout the declared breach
phase `[T+52 h, T+64 h)`, not one selected realized maximum and not the full-run
mean. This supersedes draft ambiguity item A21. Before process calibration, the
unlisted intervals `T+12..T+30` and `T+42..T+52` require one explicit versioned
interpolation or phase rule whose analytical evaluation integral is recorded.
Realized counts remain stochastic and are never forced seed by seed.

### D3 — Four synthetic coordination and authorization roles

At canonical `phi=4`, Reference uses four logical roles:

1. local/county dispatch and local-access evidence;
2. reclamation/flood-fight evidence and scoped levee actions;
3. state flood/transport evidence and scoped access actions; and
4. regional/federal specialist water/air-rescue evidence and scoped activation.

`phi` controls controller-visible evidence delivery and scoped activation
dependencies for nonlocal resources. It does not model California law, actual
Incident Command System practice, live mutual-aid agreements, staffing, or real
agency authority. Runtime records use synthetic role IDs and preserve the source
provenance behind visible messages.

### D4 — Canonical and scarcity load analyses

Canonical Reference remains `sigma=1.0, kappa=1.0`. The primary load definition
is strict compatible one-physical-resource/one-active-incident concurrent
matching with explicit unserviceable windows. Its finite trace and
unserviceable counts are **report-only**: there is no numerical load acceptance
gate and no resource or incident retuning to produce a preferred value.

The inherited approximately 4:1 value is protocol history and a sensitivity
reference, not a target. Register the following required scarcity sensitivity
before any untouched evaluation:

| Field | Value |
|---|---|
| Study ID | `reference-kappa-0p5-scarcity-v1` |
| Changed axis | `kappa=0.5` only |
| Paired world | Same seed and byte-identical non-resource exogenous artifacts as canonical |
| Primary output | Strict concurrent load trace and unserviceable-window count |
| Additional outputs | Uncapped service-unit and historical normalized sensitivity measures |
| Numerical gate | None |
| Approximately 4:1 | Report observed relation; never force or select for it |

The `kappa=0.5` inventory is a deterministic nested subset of the frozen
`kappa=1.0` roster. `kappa` changes inventory only; activation, travel, staging,
crew, authorization, degradation, hazard, truth, and observations remain under
their own mechanisms.

### D5 — Reference evidence role and paired fault profiles

Reference is the canonical full physical-loop integration and system-acceptance
scenario for later TRW/TRACE and book use. It does not alter the frozen Small or
earlier paper campaigns.

Nominal and faulted profiles share byte-identical exogenous worlds. Nominal runs
provide operational/descriptive results. Faulted runs provide prominent,
separate integration-correctness evidence for reordered observations,
authenticated false reports, identity disputes, crash/restart, silent provider
success, partial or contradictory outcomes, and failed compensation. The two
profiles are never pooled into one favorable average-effect headline.

### D6 — Base TRACE before LEAP

Implement, freeze, and validate non-LEAP TRACE Reference first. Reference may
expose stable typed action, evidence-acquisition, cost, latency, public-state,
commitment, and one-step public-belief interfaces needed by the separately
approved G3 handoff ADR. It must not include a LEAP screen, score, branch
allocator, search policy, ambiguity trigger, or budgeted-lookahead decision.

Any later TRACE–LEAP study requires a separate version, protocol, development
and selection process, untouched namespace, and incremental endpoints.

### D7 — Integration acceptance before policy-effectiveness claims

The first Reference study is an integration-acceptance study. Its primary gates
are deterministic and claim-aligned:

- byte-identical generation and replay;
- uninterrupted/restarted continuation equivalence at registered crash points;
- exactly-once provider-receipt handling and idempotent recovery;
- valid TRACE records, authorizing commitments, outcomes, revisions, and
  compensation chains;
- zero hidden-truth access by online components;
- all eight causal-axis isolation invariants;
- resource, crew, action, and commitment conservation; and
- declared runtime and memory ceilings measured in the frozen environment.

Coverage, allocation, refusal, evidence cost, valid-commitment rate,
compensation completion, reconciliation, route failure, resource utilization,
censoring, and all load measures are initially descriptive with seed-cluster
intervals. A later policy-effectiveness claim requires a separate paired and
powered protocol with cost-matched baselines, multiplicity control, and no
post-hoc endpoint substitution.

### D8 — Gauge identity and threshold operation

Every gauge identity, coordinate, unit, datum, sensor, and threshold requires a
current official source. A gauge may provide context without driving threshold
logic. A threshold is operative only when a current authoritative record
supplies its value and semantics; otherwise it is
`unavailable-non-operative`.

The verified corrections are binding for implementation: `MRU` is Middle River
at Undine Road, and `MSD` is San Joaquin River at Mossdale Bridge. Neither may
retain the erroneous specification label for narrative continuity.

## Implementation and evidence boundary

Implementation may now proceed through source binding, reduced-order physical
development, development-only coefficient fitting, non-LEAP runtime and G3
interfaces, and integration/replay testing. Every coefficient fit must identify
its spent development inputs and retain adverse diagnostics.

This amendment does not authorize:

- deriving, materializing, or running a confirmatory or holdout seed;
- treating selection or validation results as confirmatory evidence;
- changing Small files or scientific-input membership;
- using hidden truth in any online controller or predictor path;
- training or qualifying a learned Flood-SAR predictor;
- implementing LEAP decision behavior; or
- claiming operational, historical, hydrodynamic, demographic, or legal
  validity.

Any unresolved authoritative source field remains explicitly unavailable or
synthetic until a versioned source/build record supports it. A genuinely new
scientific choice that changes an estimand, authority meaning, causal axis,
resource roster, or acceptance gate requires another amendment before affected
validation.
