# WF-DFLD-01-REFERENCE protocol amendment v5

## Document control

| Field | Value |
|---|---|
| Amendment ID | `reference-protocol-amendment-v5` |
| Status | Pre-acceptance coordination-randomness correction; development only |
| Date | 2026-08-12 |
| Supplements | `reference-protocol-amendment-v1` through `v4` |
| Confirmatory authorization | None |
| LEAP authorization | None |

## Coordination common-random-number correction

The approved protocol requires a changed axis to transform its mechanism while
retaining the same underlying random draws wherever that comparison is
mathematically meaningful. The development implementation initially keyed
coordination latency and loss by evidence ID, recipient authority, and recipient
partition. Because `phi` changes the partition, this key coupled the random
realization to the axis value and prevented a controlled paired comparison.

This amendment freezes the following correction before Phase 6 acceptance:

1. Key each evidence-sharing latency and loss draw by the stable semantic pair
   `(evidence_id, recipient_authority_id)` and its draw purpose. Do not include
   `phi`, queue partition, latency limit, or loss threshold in the key.
2. Let `phi` transform the authority/partition structure, latency limit, loss
   threshold, and downstream controller-visible consequences only.
3. Record the underlying latency and loss uniform draws in the hidden
   coordination-attempt audit. They are offline scientific audit evidence and
   are never exposed to the controller.
4. Verify common random numbers dynamically on shared evidence-recipient pairs
   between canonical `phi=4` and a development `phi=5` mechanism probe. The
   probe must also verify that upstream truth, reports, and resources are
   unchanged while coordination changes.
5. Keep resource-activation draw keys independent of `phi`; `phi` may still
   change the activation latency transformation and audience.

The coordination randomness namespace, coordination artifact schemas,
generator, scenario schema, and replay manifest advance together. This
correction does not alter geography, meteorology, hydrology, exposure, latent
truth, raw observations, the resource roster, calibration coefficients, or the
registered predictor. No seed or coefficient was selected using the corrected
outcomes.

## Evidence lifecycle

All G3 and Phase 6 receipts generated before this amendment are development
diagnostics from a superseded source state. They must not be relabeled or used
as acceptance evidence. The complete non-LEAP G3 gate and Phase 6 development
acceptance are regenerated from the corrected, source-bound implementation
before any later scientific freeze.
