# Active-refresh experiment implementation notes

Status: Day 1 development protocol, subordinate to the private
`README_EXPERIMENTS.md`. These notes record implementation choices that the
canonical protocol leaves implicit. They do not freeze E1--E12, authorize test
seeds, or license a preregistration claim. G3 and all test execution remain
outside the completed Day-1 development phase.

## WP-E stochastic process and common random numbers

For route `r` over a simulator step of length `dt`, the depth increment is

```text
drift_r * dt + sigma_r * sqrt(dt) * z(seed, simulation_time)
```

where `drift_r = water_rise_rate * forcing * susceptibility_r`,
`sigma_r = water_rise_rate * forcing_noise_std * susceptibility_r`, and one
common standard-normal forcing innovation is shared by all routes at the same
simulation time. This is a declared perfectly correlated regional forcing
factor, not accidental independent route noise. The global water level uses the
same innovation with susceptibility one.

Depth is reflected at zero because negative physical water depth is invalid.
The exact theorem check must therefore remain the separate unclipped synthetic
WP7 scalar test. R-B is described as a continuous diffusion evaluation regime,
not a literal test of the theorem's zero-drift assumptions.

Randomness uses a versioned, stateless SHA-256 key derivation. Keys encode types
unambiguously and encode floating-point simulation time with `float.hex()`;
Python's process-randomized `hash()` and draw-order-dependent RNG state are not
used. The namespaces are disjoint:

- `env.forcing`: seed, step start time;
- `obs.drone.delivery`: seed, route, asset, observation time;
- `obs.drone.accuracy`: seed, route, asset, observation time.

Policy execution can neither consume nor shift the exogenous stream. Different
policies must have identical depth trajectories for a shared seed and time grid.

## Zero-noise compatibility oracle

The five predeclared compatibility seeds are `1, 2, 3, 4, 5`. The oracle is a
canonical semantic event projection against clean commit `11c6661`, because raw
event bytes contain intentionally nondeterministic UUIDs, wall-clock timestamps,
and derived hash-chain values. The projection removes only `event_id` and
`created_at`; it retains sequence, simulation time, event type, visibility,
source, scenario level, schema version, and the complete payload. The test also
compares complete truth trajectories. No new TICK payload field is emitted when
`forcing_noise_std == 0`.

## Development-only G2 definition

Before the first pilot, G2 is defined as the pooled diagnostic

```text
sum(executed_stale) / sum(executed)
```

over R-B, no-refresh, seeds 1--20. Every run must finish, every seed must have a
proposed commitment, and the pooled executed denominator must be nonzero.
Per-seed proposed, executed, executed-stale, held, escalated, and coverage are
retained. Coverage is `executed / proposed` and is reported beside every
staleness value. The target interval `[0.1, 0.4]` is a development gate, not an
inferential result.

At most three total noise settings may be evaluated, including the initial
`0.35`. If the initial result is below the interval, evaluate `0.70`; if above,
evaluate `0.00` as a diagnostic endpoint. One final bracket midpoint may be
evaluated only if the observed direction is monotone. A direction reversal
fails the tuning heuristic rather than permitting post-hoc selection. Only a
positive-noise value may pass G2.

`executed_stale` is the paper's false-at-execution estimand: the
commitment's action-specific truth oracle says the recorded claim is false at
`ACTION_STARTED`. Expiration of a clearance/authorization interval is retained
as `authorization_outside_tolerance` but is not added to the stale numerator.
The runner independently replays truth and recomputes this label; it rejects an
event payload or sidecar that disagrees with the replay oracle.

Controller forecasts start from controller-visible route beliefs, observed
depth/status, and declared S2 dynamics. Current latent route depth is not an
input to the predictor. Route-threshold probability, rather than whole-mission
failure probability, drives the binary consequence and channel models.

## Comparator, gate, and smoke semantics

Fixed-interval and validity-clock are timing comparators. When due, both use
the same predeclared first available channel order (`gauge_poll`, then
`drone_survey`) without conditioning the scheduled acquisition on adaptive
VoI. Adaptive routing alone uses adequate-set-first positive net value. Channel
adequacy is computed preposteriorly by passing each binary channel outcome
through the unchanged effective gate (`configs/policies/trace_v1.yaml`),
including delivery probability and latency. `trace_exp_v1.yaml` remains a
provisional E11 input and is not represented as active before G3.

The Day-1 structural smoke matrix is fixed here as three representative
non-control configurations over seeds 1--3: `fixed-k:45`, `clock:0.55`, and
`adaptive:1`. It is not an inferential comparison. It runs only after G2 passes
and requires identical per-seed exogenous projections across all three cells.

## Harness integrity and acceleration

Every cell has a fingerprint covering the complete request, source tree,
scenario, shock registry, protocol, effective gate, RNG schema, and Python
environment. Resume requires an exact fingerprint match. Sources and inputs are
hashed both before and after simulation; a change during a run fails the cell.
Artifacts are staged, hash-inventoried, independently re-derived from events,
and atomically published only after validation.

The unmodified event and TRACE repositories reparse their complete JSONL files
on every operation, which makes the 7,200-tick pilot quadratic. The evaluation
runner uses run-local append caches that preserve their exact JSONL/hash-chain
byte contracts. Published logs are then verified by the original unmodified
repositories. A byte-equivalence regression test and two independent
full-horizon reruns guard this optimization; it changes no simulated state,
event ordering, RNG draw, or policy behavior.

## G2 workload amendment 1

The original Day-1 G2 is preserved as a valid failed gate. Its workload ended
at 75 s, whereas route closure occurred near 6,300--6,700 s, so it provided no
false-at-execution exposure. A versioned later-horizon amendment was introduced
to create meaningful exposure without changing the physical dynamics. The
authoritative protocol record remains outside the repository.

A late call alone is insufficient because the original route report has too
little support by the boundary window and the unchanged gate would HOLD. The
amended workload therefore has no time-zero demand, gives every policy the same
exact `south_detour` gauge sample at 6,420 s (delivered at 6,425 s, cost 0.2),
and issues one four-person Riverside call at 6,443 s with absolute deadline
7,643 s. The run horizon is 7,800 s. This retains the physical water process,
closure threshold, gate, and false-at-`ACTION_STARTED` estimand. The comparator
is consequently named **no discretionary refresh**, because the common gauge
is a workload baseline rather than a policy-selected refresh.

Seeds 21--40 are reserved for implementation QA. The untouched amended G2
pilot uses development seeds 41--60, one frozen noise setting (`0.35`), and no
post-launch retuning. The target remains the pooled inclusive interval
`[0.10, 0.40]`. Smoke uses seeds 41--43 and runs only if amended G2 passes.
Validation and test partitions remain unopened.

## Post-smoke measurement correction

Amendment-1 smoke exposed that the controller emits a new TRACE record version
for the same stable `plan_id` every five seconds while a plan remains held. The
v1 commitment sidecar correctly retained those revisions for audit, but WP5's
aggregate mistakenly counted every revision as a newly proposed commitment.
That made coverage depend on replanning cadence and run horizon, contrary to the
paper's declared unit of analysis: each dispatch, dock selection, or rendezvous
commitment.

Measurement amendment 2 preserves every row in `commitment_ledger.jsonl` and
adds `commitment_unit_ledger.jsonl`, which collapses revisions by stable
`plan_id`. Primary `proposed`, disposition, and coverage metrics are computed
from commitment units; `proposal_records` reports the raw revision count beside
them. A unit that ever executes is executed, otherwise an escalation is
retained, and all remaining units are held. Stable record identity, ordered
versions, and at most one execution per unit are independently validated.

The correction also reports verification cost as the sum of common workload
evidence and discretionary refresh, while retaining both components. It does
not change the workload events, stochastic process, gate, stale-execution
estimand, adaptive rule, policy parameters, or G2 target. The zero-execution
adaptive smoke cells remain an observed consequence of the paper's
adequate-set-first rule, not a target for post-hoc tuning. Coverage and the RQ3
false-HOLD components are the declared safeguards against rewarding abstention.

This is a development-only implementation correction motivated by smoke. It
does not retroactively replace amendment-1 evidence or authorize validation.
The rerun reuses development seeds solely for regression and gate continuity;
it has no confirmatory or inferential status.

## Deferred until G3

- Final E1--E12 values and policy manifest.
- Validation-derived budget quartiles and operating points.
- Test sample size and stopping rule.
- Any validation or test-seed execution.
- Any claim that the protocol is frozen or preregistered.
