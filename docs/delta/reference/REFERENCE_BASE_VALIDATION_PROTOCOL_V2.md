# WF-DFLD-01-REFERENCE base validation protocol v2

## Status and scope

This protocol is approved and frozen as an input, but its protected study is
not yet authorized for execution. It implements Amendment v6 without deriving
or materializing any `selection-v2` or `validation-v2` value in the local
checkout.

The study evaluates the non-LEAP base Reference integration. It does not select
a policy, compare TRACE with LEAP, estimate field reliability, or support an
operational-readiness claim. `selection-v2` therefore remains reserved and
disabled. A future LEAP or policy-effectiveness experiment requires its own
estimands, margins, multiplicity policy, power analysis, and protected
namespaces.

## Population and inference

The original integration study comprises exactly 100 independent missions from
the protected `validation-v2` namespace. A mission seed is the sampling and
bootstrap unit. Counts, fractions, costs, load summaries, recovery quantities,
and other operational outputs receive deterministic 10,000-resample
mission-cluster intervals. These intervals are descriptive; no operational
metric has a numerical pass band.

Canonical `kappa=1.0` remains the primary base configuration. The registered
`reference-kappa-0p5-scarcity-v1` run is paired within seed and changes inventory
only. It is a report-only sensitivity and does not target a preferred load
ratio.

## Deterministic integration gates

The exact gates cover causal-axis isolation, chain integrity, conservation,
exact replay and publication, registered fault reachability, hidden-truth
separation, restart equivalence, Small preservation, source/security controls,
and canonical resource ceilings. Gate failure is valid study evidence. The
executor records and publishes it rather than changing coefficients, replacing
seeds, or suppressing the mission.

## Protected lifecycle

`selection-v1` and `validation-v1` were exposed by development tests and are
permanently superseded before scientific use. The v2 protocol file contains no
protected values. The validation list can be produced only after the following
all verify:

1. the exact annotated authorization tag and checked-out source commit;
2. workflow run attempt one and absence of a prior successful original for the
   same workflow, tag, and commit;
3. the complete scientific-input manifest and derived freeze record;
4. the digest-pinned Python 3.11 Linux environment and hash-locked dependency
   set; and
5. a separately granted external authorization to push the tag.

The remote workflow derives the list once, runs 20 five-mission shards with the
scientific process offline, and aggregates exactly 100 mission receipts. Raw
seed values are never accepted as workflow inputs or printed to ordinary logs.
The original report binds the source, workflow/run identity, protocol, freeze,
environment, lock, seed-list digest, shards, gates, intervals, and all adverse
findings.

## Reproducibility identities

The normative machine-readable protocol is
`data/scenario/delta/reference_protocol/reference_base_validation_protocol_v2.json`.
The generated scientific-input manifest and freeze record are excluded from
their own input inventory to avoid self-reference. The freeze record binds both
artifacts plus the original workflow, corrected G3 handoff, corrected canonical
Phase 6 evidence, environment contract, and lock.

Replication remains disabled until the original report is committed with a
byte-exact registry. Any later authorized execution must identify itself as a
replication and cannot replace the original.
