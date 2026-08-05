# G3 experiment-freeze review

Status: **unsigned review draft**. No test seed has been enabled, generated, or
executed. The proposed freeze tag remains `exp-freeze-v1` and must not be
created until professor sign-off.

## Completed before G3

- R-B validation executed the registered 19 configurations on seeds 101--125:
  475/475 cells completed and passed independent artifact validation.
- Every cell used `forcing_noise_std = 0.35`, the registered later-horizon
  validation workload, one-second ticks, a 7,800-second amended horizon, and
  the provisional `trace_exp_v1.yaml` gate.
- Each seed's exogenous trajectory was byte-identical across all 19 policies.
- All cells share one source-tree hash, environment hash, workload hash, and
  gate-policy hash.
- Validation result hash:
  `3ad8da383d90413b6c2cf1d51b102a410f0ab8f510ad2ed339d1b64fe70ee7ab`.
- Scientific source-tree hash:
  `d66b6148d018882d6e32f9e658c579f0622126fd8449ef64bda1b90613b8b0a7`.

## Validation-derived freeze values

The predeclared Hyndman--Fan type-7 quartiles of all 475 total validation
costs are:

| Budget | Cost |
|---|---:|
| B1 | 0.2 |
| B2 | 0.2 |
| B3 | 0.4 |
| B4 | 1.8 |

The deterministic selection rule is minimum pooled stale-execution rate among
configurations with mean cost at or below the budget. Undefined staleness from
zero execution is ineligible. Ties use lower mean cost and then lexical policy
specification.

| Family | B1 | B2 | B3 | B4 |
|---|---|---|---|---|
| No refresh | `none` | `none` | `none` | `none` |
| Fixed interval | infeasible | infeasible | `fixed-k:120` | `fixed-k:120` |
| Validity clock | `clock:0.25` | `clock:0.25` | `clock:0.25` | `clock:0.25` |
| Adaptive | `adaptive:1` | `adaptive:1` | `adaptive:1` | `adaptive:1` |

The resulting unique provisional test set contains four configurations, not
the planning estimate of thirteen.

The development pilot gives `s_pilot = 0.4569367667` under the stated
per-seed estimator. The unbounded formula gives 1,284 seeds, so the declared
cap binds and `n_test = 120`.

## Results that must not be overclaimed

- No refresh: 6/26 stale executions (`0.2308`), coverage 26/59 (`0.4407`),
  mean cost `0.2`.
- Selected adaptive: 0/7 stale executions, coverage 7/57 (`0.1228`), mean
  cost `0.2`.
- Adaptive settings executed only 5--7 commitments across 25 missions. Their
  zero observed staleness therefore does not establish superiority; the low
  coverage is a major result and limitation.
- `fixed-k:5` executed no commitments, so its staleness is undefined and it
  was excluded rather than assigned zero.
- Several configurations are observationally tied. The deterministic
  tie-break makes the freeze reproducible but does not imply their parameters
  are empirically distinguishable.

## Professor decisions requested at G3

1. Confirm whether the discrete/duplicated budgets and absent fixed-k points at
   B1/B2 are acceptable under the frozen quartile rule, or require a versioned
   pre-test amendment.
2. Confirm that the low adaptive coverage is an intended negative/development
   result to carry into test, rather than a reason to revisit the operating
   rule before freeze.
3. Confirm the `s_pilot` wording. Zero-execution development seeds were omitted
   because their stale-execution fraction is undefined; the 120-seed cap binds
   regardless.
4. Confirm the amended 7,800-second operational horizon against E8's nominal
   two-hour value. The additional 600 seconds are required to observe the
   approved late incident through its deadline.
5. Confirm use of the provisional four-class `trace_exp_v1.yaml` gate. G2 used
   the earlier development gate, while all validation cells used E11's
   provisional experiment gate.
6. Confirm the seven-entry ablation inventory and all remaining E1--E12 values
   in `manifest.yaml`.

After those decisions and an explicit signature, the exact reviewed source
and manifest can be committed and tagged `exp-freeze-v1`. Test execution must
remain disabled until that freeze exists.
