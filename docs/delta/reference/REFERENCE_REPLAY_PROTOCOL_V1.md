# WF-DFLD-01-REFERENCE development replay protocol v1

## Status and claim boundary

This protocol covers deterministic development artifacts for the non-LEAP
Reference simulator. It is not a validation registration and does not authorize
confirmatory-seed access. The bundle records development results descriptively;
statistical claims require a later approved and immutable validation protocol.

## Deterministic boundary

One bundle is determined by the scenario seed, the complete generated scenario,
the nominal base runtime profile, the selected predictor provenance, the direct
input-file inventory, and the Python source-tree digest. The manifest records the
scenario and runtime prefix digests and independently hashes every artifact.

The Reference-specific environment contract identifies the digest-pinned Python
3.11 target and complete dependency lock. Binding that contract is distinct from
claiming that a particular run used it; only a separately verified execution
receipt may make the latter claim.

Execution metadata such as host name, wall-clock time, and GitHub run identity is
not part of the scientific artifacts. A later execution receipt may record those
facts without changing otherwise identical scientific output.

## Artifact separation

Controller-visible artifacts are separated from hidden evaluation artifacts.
Public files contain no truth-incident or truth-person identifiers. Hidden files
include physical truth, synthetic exposure, incident candidate audits, report
lineage, resource truth/audits, coordination attempt audits, registered fault
applications, and the complete mixed-visibility event chain. A separate public
event projection contains only controller-visible events.

TRACE persistence is exported in two forms: consumer-friendly model arrays and
the canonical hash-chain envelopes for evidence, records, and commitments. The
manifest binds both forms and their terminal prefix digests. Capacity output is
aggregate-only and remains development/report-only under the separately defined
capacity protocol.

## Resource bounds and security

Canonical files are written independently rather than constructing a second
in-memory bundle. Each artifact is limited to 128 MiB and the registered bundle
to 512 MiB. Direct inputs are caller-rooted, bounded, regular files. Replay roots
and intermediate directories may not be symlinks, and writes are atomic.

The seed-20260812 development profile measured approximately 30 MiB of generated
scenario JSON and 25 MiB of runtime-event/result JSON before the additional
consumer projections. A complete generate, run, and capacity evaluation measured
12.79 seconds with peak resident memory of approximately 268 MiB on the local
development host. The focused artifact and exact-replay tests execute the two
runs sequentially.

## Verification

Exact replay first verifies the reference manifest and every registered artifact,
then checks the current direct-input inventory and source-tree digest before any
regeneration. It executes into an empty root, compares the regenerated manifest,
and performs bounded streaming byte comparison for every registered file.

Tampering with an artifact or the manifest, changing a direct input, changing the
source tree, crossing a symlink boundary, or writing into a nonempty output root
fails closed. Runtime and replay use no network access.

## Deferred work

The following remain outside this development protocol:

- the unresolved latent-incident burden and observation-volume calibration;
- a canonical OCI execution receipt proving the actual runtime matched the bound contract;
- a registered development/confirmatory statistical report;
- a committed, calibrated Reference bundle and its registered publication figures;
- LEAP policy, search, scoring, or budget behavior.
