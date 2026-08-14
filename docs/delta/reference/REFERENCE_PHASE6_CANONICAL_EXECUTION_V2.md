# Reference Phase 6 canonical execution v2

## Correction

The v1 canonical receipt preserved a runner-label limitation: its outer
container receipt was canonical, while the raw runner had classified itself as
`local-preflight`. Amendment v6 corrected the runner so it inspects the exact
environment in process and derives the role from the typed verification result.

A v2 canonical run is accepted only when the raw resource receipt records:

- schema `delta-reference-phase6-resource-receipt-v2`;
- `measurement_role=canonical`;
- the exact environment-contract and dependency-lock hashes;
- no environment mismatch; and
- `canonical_gate_status=passed` under all three frozen resource ceilings.

The outer v2 execution receipt additionally binds the pinned OCI index and
Linux/amd64 platform-manifest digests, source commit, complete scientific-input
aggregate, raw core receipt, exact replay, and deterministic publication
regeneration. This is canonical development preflight evidence; it provides no
validation, selection, confirmatory, or LEAP authority.

The original v1 receipt and documentation remain protocol history. The v2
receipt supersedes only the incorrect raw-label interpretation and does not
alter simulator mechanics, coefficients, seeds, axes, resources, faults,
policy, or reported load definitions.
