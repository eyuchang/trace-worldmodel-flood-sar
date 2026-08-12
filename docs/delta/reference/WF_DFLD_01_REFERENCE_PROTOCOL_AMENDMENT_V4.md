# WF-DFLD-01-REFERENCE protocol amendment v4

## Document control

| Field | Value |
|---|---|
| Amendment ID | `reference-protocol-amendment-v4` |
| Status | Approved-scope observation-calibration rule; development only |
| Date | 2026-08-12 |
| Supplements | `reference-protocol-amendment-v1` through `v3` |
| Confirmatory authorization | None |
| LEAP authorization | None |

Amendment v1 decision D2 is controlling: the synthetic breach-phase report
intensity is 95 reports/hour throughout the 12 half-open one-hour bins in
`[T+52 h,T+64 h)`. D2 explicitly supersedes ambiguity item A21 in the original
draft. The 95/hour quantity is an ensemble expectation; no seed is forced to
realize it.

## Rate-table reconciliation

The inherited rate table and the approximately 2,900-report total are
arithmetically inconsistent when used without an interpolation rule. This
amendment freezes the missing rule before observation fitting:

1. Use the inherited hourly rates of 9 for R0, 26 for `T+30..T+42`, 95 for
   R3, and 40 for `T+64..T+96`.
2. Interpolate linearly, evaluated at each one-hour bin midpoint, from 9 to 26
   across `T+12..T+30` and from 26 to 95 across `T+42..T+52`.
3. Preserve every R3 bin at 95. The unscaled non-breach integral is 2,620
   expected reports and the breach integral is 1,140.
4. Multiply every non-breach bin by the exact rational factor `88/131`. The
   non-breach integral becomes 1,760 and the complete 96-hour integral becomes
   exactly 2,900.

The scaled curve is a synthetic observation-process design target, not a field
estimate. Both the unscaled conflict and the scale factor must appear in the
fit report.

## Truth-linked observation mechanism

The existing lossy zero/one/many channel remains the base process. Calibration
may alter one global initial-report probability and add independently keyed,
incident-linked witness opportunities. Every supplemental report must point to
an already generated latent incident in hidden scoring data, use only the
nonunique public vocabulary, and remain subject to callback, delivery,
location, taxonomy, and communication loss. It must never create truth or
expose a hidden identifier to the controller.

Use one fixed maximum number of witness opportunities per incident. Fit one
global initial-report coefficient and one fixed hourly witness probability
vector across the 100 already-spent `development-v1` seeds. The hourly vector
is justified by the inherited nonhomogeneous observation schedule; it is not a
per-seed solution. Select the largest preregistered initial-report candidate
whose analytical hourly witness probabilities are all feasible, preserving as
much direct incident reporting as the fixed rate curve permits. Tie-break on
the lower maximum witness probability and then the lower candidate value.

Record the analytical expectation, stochastic development realization,
hour-by-hour residuals, channel relationships, public taxonomy, nonreporting,
and every candidate. In particular, disclose the incompatibility between the
peak public-taxonomy percentages in the original sketch and the approved
low-severity latent composition. Do not relabel incidents or fabricate rescue
truth to match that table.

## Stop boundary

Benchmark the exact two-pass fitting path before executing all 100 spent
development seeds. The existing 15-minute wall-time, 2-GiB peak-memory, and
1-GiB additional-disk gates apply. No selection, validation, confirmatory, or
holdout seed may be derived, materialized, or run, and no LEAP behavior is
authorized by this amendment.

The first benchmark regenerated each complete world for its stochastic second
pass and projected 16.94 minutes after the registered margin. Preserve that
failure as adverse evidence. A subsequent benchmark may retain a compact
per-incident sufficient-statistics record from the first pass and replay the
same keyed report draws from it, provided representative-seed tests prove exact
hour, relationship, and taxonomy count equality with full draft generation.
This is a computational optimization only; it may not omit an incident or
change a draw key, probability, schedule, seed, objective, or selection rule.
