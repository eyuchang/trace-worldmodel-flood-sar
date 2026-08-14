# WF-DFLD-01-REFERENCE canonical Phase 6 execution

## Status

This receipt records a development-only execution of the frozen Phase 6 core on
commit `45a0192f4f25f1a29f9aecc57c61247ab5415127`. It verifies the registered
Python 3.11 Linux environment, exact replay, deterministic publication, and the
registered resource ceilings. It supplies no selection, validation, holdout,
confirmatory, policy-effectiveness, or LEAP authority.

## Frozen inputs

| Input | SHA-256 |
|---|---|
| Scientific-input aggregate | `9f12ed0993ac11fd3636e0a195fb21ae442829930f94f531135e7e2c0c4194b5` |
| Environment contract | `5fbbb91bc556ab8483b0db19563cf28117ac24a5c142eda200c48d86d501019d` |
| Python 3.11 dependency lock | `06b286ad1b4b4d2397af27e567de3c207db59e67400d329edd214032d58355e1` |
| OCI index | `3b3706a90cb23f04fabb0d255824f9a70ceb46177041898133dd5a35f3a50f0a` |
| Linux/amd64 OCI platform manifest | `88b6d3132a0850db3587a4f4ff28d5568e7d65ff99f0ee34f42be864ddb4ca1d` |
| Reference-only Dockerfile | `68f6d864a413d3c5800455ebf708278231d06442bc82d67b328161ba0bb4bd22` |
| Derived Reference execution image | `4ce5a72b8141ee77c4a66cd34b600a9cbf07aaf2a6921af3fe4dd0b4f46011ad` |
| Execution-receipt writer | `19c713e3b0582e042089b8523c318ca67f8c2032d910937ab0302b831dda7d5b` |

The pinned index was resolved to its registered `linux/amd64` platform
manifest before the image was built. The lock was installed with hash
verification. The receipt records the complete installed distribution
inventory and the versions of Python, GDAL, GEOS, and PROJ. The run used UTC,
the `C.UTF-8` locale, and `PYTHONHASHSEED=0`.

The base image and locked packages were acquired during image preparation.
The scientific execution itself ran with networking disabled, a read-only root
filesystem, a read-only repository mount, a one-CPU limit, a 2-GiB memory and
swap limit, and a 512-process limit. No unrelated image or container was
modified.

## Results

| Check | Result |
|---|---|
| Python | `3.11.14` |
| Platform | Linux `x86_64` |
| Environment and lock verification | Pass; zero mismatches |
| Frozen Phase 6 core checks | Pass |
| Exact replay | Byte-identical |
| Publication regeneration | Byte-identical |
| Replay-manifest digest | `165b4dc63021e3b6096f661ce91c6e78b02ea33891f1ce33206737807177a686` |
| Publication-manifest digest | `49486bd58a4dbb5cbefdb6877c0377bb545763e0bdce3ec4d7a8cfef19ae795e` |
| Wall time | 595.511 seconds; limit 900 seconds |
| Peak resident memory | 1,295,437,824 bytes; limit 2,147,483,648 bytes |
| Transient output | 867,818,562 bytes; limit 1,073,741,824 bytes |

The raw core receipt is
`data/scenario/delta/reference/phase6_canonical_v1/canonical_raw_core_receipt.json`
(file SHA-256
`6407411938a4890826bae9a457b757eaf1d9aa4590cddb9a554d3d224f29ea1d`).
The independent environment/execution receipt is
`data/scenario/delta/reference/phase6_canonical_v1/canonical_execution_receipt.json`
(file SHA-256
`5932902de036cc174932070e2b28b424658ad63350c5a9c268052b378f20ef22`,
internal receipt digest
`4426bc6b84b2104c14be3098dd5af81b10c03ef8da555bef945a26dc2be5172c`).

## Preserved limitation and required correction

The frozen Phase 6 runner currently assigns `measurement_role=local-preflight`
and `canonical_gate_status=pending-canonical-environment` to every direct
resource receipt. Those values are hard-coded; the runner cannot identify an
otherwise matching canonical execution. The raw receipt therefore remains
unaltered and retains those labels. The independent execution receipt verifies
the actual environment and resource observations without relabeling the raw
scientific output.

Before the Reference validation protocol is frozen, the runner should accept a
typed, verified environment identity and derive the measurement role from an
exact contract/lock/platform match. The canonical Phase 6 check must then be
rerun after the resulting scientific-input manifest changes. This is an
execution-provenance correction, not a reason to change the simulator,
coefficients, seed, or resource ceilings.
