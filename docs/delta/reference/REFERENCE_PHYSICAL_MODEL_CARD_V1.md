# WF-DFLD-01-REFERENCE reduced-order physical model card v1

## Intended use

`delta-reference-physical-v1` is a deterministic teaching and systems-testing
model for the Reference TRACE integration workload. It supplies timed weather,
gauge-stage components, a scripted breach, island storage, and crossing-state
changes. It is designed to test evidence freshness, access loss, commitments,
recovery, and compensation. It is not a hydrodynamic forecast, an emergency
operations product, or a reconstruction of the 1972 Andrus event.

The model operates from `T-48h` through `T+96h` on a 300-second grid. The
controller never receives future samples. Hidden breach/storage truth and
controller-visible environment samples are separate hash-chained events.

## Meteorology

The nine half-open phases cover the complete burn-in and evaluation windows
without overlap or gaps. Each phase declares nominal rain, wind, ceiling, and
air-operability values. The supplied sketch's evaluation rates integrate to
15.18 inches, while the same sketch separately states 9.8 inches. The runtime
preserves both facts: it emits the nominal rate and applies one disclosed global
factor `9.8 / 15.18` to obtain effective rainfall. This is a protocol
reconciliation, not empirical calibration.

`sigma` multiplies rain and wind only. It does not change geography, resource
inventory, authority structure, observation quality, or predictor identity.

## Gauge stage

Every sample exposes the integer fixed-point identity

```text
stage = baseline + M2 tide + lagged runoff + wind setup + release
```

The M2 period is 44,700 seconds (12 h 25 min), with gauge-specific phase and
amplitude plus a smooth synthetic spring-tide envelope centered at `T+66h`.
Runoff is a gauge-specific lagged response to effective rain. Wind setup is
capped at 0.8 ft. The synthetic upstream-release contribution begins at `T+20h`
and ramps for six hours.

These components support audit and controlled intervention; their coefficients
have not been fitted to CDEC time series. `MRU` is correctly identified as
Middle River at Undine Road and `MSD` as San Joaquin River at Mossdale Bridge.
All seven gauge thresholds are `unavailable-non-operative`. Generated stage is
never described as a CDEC observation or prediction.

## Scripted breach and island storage

`BREACH-01` activates at `T+52h` on the synthetic segment
`SIM-RD407-WEST-01`. The segment is anchored conceptually to the source-bound
Andrus footprint but is not a survey geometry and makes no legal maintenance or
ownership claim. Width increases from 60 ft to 210 ft over nine hours. Inflow
combines a width-scaled positive mean with an M2 term large enough to reverse
direction. Storage integrates signed inflow, never falls below zero, and is
capped by the declared synthetic 76,000 acre-foot capacity.

First-street and one-third-city states are deterministic teaching delays at six
and fourteen hours after activation. They are event-design markers, not
validated depth-damage or inundation forecasts. Casualties are not modeled.

## Access rules

Crossing states are versioned scenario rules, not live operability claims.
`XNG-04` closes at `T+53h` as the scripted breach access effect. Real McCoy and
J-Mack suspend when the model wind or model-stage rule is met. The catalog keeps
`XNG-10` unavailable because its current crossing type and completion status
remain unresolved in the reviewed official evidence. Other crossings are
normally open in this version.

The route graph is explicitly simulation-grade. It must not be used for
navigation, dispatch, clearance, or travel-time advice.

## Reproducibility and tests

The implementation uses integer public artifacts where practical and canonical
JSON for event payloads, hashes, state, and checkpoints. Tests verify:

- complete and contiguous phase/timeline coverage;
- additive gauge identities and non-operative thresholds;
- the disclosed rainfall reconciliation;
- breach onset, widening, tidal reversal, storage bounds, and access closure;
- hidden/public event separation;
- event-chain tamper detection; and
- byte-identical checkpoint/restart replay.

Development tests do not constitute hydrologic validation or operational
qualification. No confirmatory Reference seed has been derived or executed.
