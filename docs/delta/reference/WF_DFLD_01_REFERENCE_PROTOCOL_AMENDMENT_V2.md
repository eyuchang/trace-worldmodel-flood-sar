# WF-DFLD-01-REFERENCE protocol amendment v2

## Document control

| Field | Value |
|---|---|
| Amendment ID | `reference-protocol-amendment-v2` |
| Decision set | `reference-scientific-decisions-v2` |
| Status | Approved implementation basis; development only |
| Approval date | 2026-08-12 |
| Approved by | Jay Roy, project owner |
| Supplements | `reference-protocol-amendment-v1` |
| Confirmatory authorization | None |
| LEAP authorization | None |

Jay approved the latent-workload design in this amendment before coefficient
fitting. Amendment v1 remains controlling for its eight decisions. This
amendment resolves only the latent-incident scale that v1 left open.

## Approved latent-workload design

At the canonical axes, the 96-hour evaluation interval `[T0,T+96 h)` shall
contain a stochastic synthetic workload with an ensemble mean in the inclusive
design band **1,800--2,200 latent incidents**. Development fitting uses the
band midpoint, 2,000, as its symmetric objective. Burn-in incidents are reported
separately and do not enter this target.

The workload is explicitly synthetic and nonempirical. It represents
information demand, public-hazard reporting, welfare checks, and access
disruption at the scale needed to exercise TRACE's full physical and evidence
loop. It is not an estimate of real Delta emergency incidence, morbidity,
casualties, unmet need, or agency workload.

The target composition is frozen before fitting:

| Latent incident type | Target share | Interpretation |
|---|---:|---|
| `information_need` | 36% | Route, shelter, access, and protective-action questions |
| `hazard_response` | 27% | Utility, debris, road, crossing, and access hazards |
| `welfare_check` | 18% | Synthetic vulnerable-person and contact checks |
| `levee_inspection` | 7% | Non-breach anomaly inspection workload |
| `animal_rescue` | 4% | Synthetic livestock or companion-animal access need |
| `missing_person` | 3% | Synthetic movement/contact uncertainty |
| `stranded_structure` | 2% | Occupied shallow-ponding rescue need |
| `vehicle_rescue` | 1.5% | Vehicle/access rescue need |
| `medical_access` | 1.5% | Access-limited medical transport need |

The first four categories together account for 88% of the target workload.
The three direct human rescue/medical categories (`stranded_structure`,
`vehicle_rescue`, and `medical_access`) total 5%. The proportions are synthetic
mechanism-design values, not empirical frequency estimates. The fit report must
show realized development composition and all residuals rather than relabeling
episodes to force these shares.

## Required fit sequence

1. Benchmark a non-scientific scale fixture before multi-seed fitting. Stop and
   report before work projected to exceed 1 GiB of additional disk, 2 GiB peak
   resident memory, or 15 minutes wall time.
2. Fit incident-type intercepts using only the already spent 100-seed
   `development-v1` namespace. Do not use the illustrative seed `20260812` as a
   separate objective and do not access selection, validation, confirmatory, or
   holdout seeds.
3. Record every evaluated coefficient vector, objective component, seed-level
   total, taxonomy residual, convergence decision, input digest, and adverse
   diagnostic. Freeze one global coefficient vector; never normalize a seed.
4. Only after the truth coefficients are frozen, fit the observation channel on
   the same spent development seeds to the existing approved targets: an
   expected 2,900 controller-visible evaluation reports and 95 reports/hour
   throughout `[T+52 h,T+64 h)` at `iota=0.7`.
5. The observation fit must not alter truth, fit per seed, or use the public
   report target to create truth incidents. It must record the analytical phase
   schedule, every candidate, development residuals, channel diagnostics, and
   adverse results.

The call-taxonomy percentages in `DELTA_SCENARIO_SPEC.md` remain public-report
process targets, distinct from the latent truth composition above. The
observation calibration report must disclose any conflict between those public
targets and the low-severity latent design; it may not fabricate unique hidden
lineage, silently reclassify truth, or claim empirical calibration.

## Evidence and stop boundary

Development results may support engineering calibration and constructed G3
integrity evidence only. They do not support operational, epidemiological,
historical, demographic, predictor-effectiveness, or policy-effectiveness
claims. No confirmatory or holdout seed may be derived, materialized, or run
under this amendment, and no LEAP behavior is authorized.
