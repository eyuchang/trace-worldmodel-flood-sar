# WF-DFLD-01-REFERENCE Phase 6 development acceptance

## Status and authority

| Field | Value |
|---|---|
| Protocol ID | `reference-phase6-development-acceptance-v1` |
| Scenario | `WF-DFLD-01-REFERENCE` |
| Scientific role | Development integration acceptance; non-inferential |
| Authorized seed | Illustrative/spent development seed `20260812` |
| Selection authority | None |
| Validation authority | None |
| Holdout or confirmatory authority | None |
| LEAP behavior | Excluded |

This protocol operationalizes Phase 6 of the approved Reference protocol and
Decision D7 of Amendment V1. The harness does not fit coefficients, tune policy,
change estimands, alter the resource roster, replace the fault schedule, or
select acceptance ceilings. Material pre-acceptance defects found by the
harness must be corrected through a separately versioned amendment and require
all affected evidence to be regenerated. Amendment V5 records the coordination
common-random-number correction found during this process.

## Required evidence

The acceptance harness must bind its complete scientific-input inventory and
produce deterministic, typed results for the following requirements:

1. the scenario and nominal runtime regenerate deterministically from the spent
   development seed;
2. nominal execution completes and the registered fault profile exercises every
   fault family;
3. restart produces the same public and durable continuation as uninterrupted
   execution;
4. event, evidence, TRACE, commitment, authorization, outcome, correction, and
   recovery joins verify;
5. public runtime artifacts contain neither hidden lineage fields nor hidden
   truth identifiers, and deleting hidden lineage cannot change public runtime
   decisions;
6. each of the eight approved axes passes its causal-isolation invariant under
   keyed common random numbers;
7. resources, crews, commitments, outcomes, and active service intervals obey
   one-resource/one-incident conservation and censoring semantics;
8. strict, uncapped, historical, and residual capacity accounting satisfies all
   typed conservation checks without converting an unserviceable state into a
   finite ratio;
9. clean replay reproduces every registered byte, and deterministic publication
   regeneration reproduces every figure and result-table byte;
10. the run remains offline and respects the approved 15-minute wall-time,
    2-GiB peak-memory, and 1-GiB transient-output ceilings when measured in the
    canonical Python 3.11 environment.

No numerical load target, policy-effectiveness endpoint, coefficient target, or
population-level statistical claim is part of this gate.

## Execution boundary

The harness uses only seed `20260812`, which was already consumed for Reference
development and G3 characterization. It must not import the Reference seed
derivation module, materialize another seed, or read a selection, validation,
holdout, or confirmatory registry.

The registered semantic fault schedule remains
`reference_fault_schedule_v1.json`. The corrected G3 handoff manifest is a
required input and remains explicitly non-LEAP. Fault and nominal execution must
share byte-identical exogenous scenario inputs. The Phase 6 fault stage must run
the registered G3 execution with sockets disabled and wrap the complete integrity
report in a digest-bound `delta-reference-phase6-fault-receipt-v1`; a bare G3
report is not sufficient for the Phase 6 offline check.

## Resource measurement

Resource observations are execution receipts, not scientific results. A receipt
must distinguish:

- `canonical`: the digest-pinned Python 3.11 Linux environment, in which the
  three ceilings are acceptance gates; and
- `local-preflight`: any other environment, where measurements are diagnostic
  and canonical gate status remains pending.

Wall time is measured with a monotonic clock. Peak resident memory is measured
in a fresh dedicated process using the platform's `getrusage` semantics. Disk
usage includes all replay, runtime-store, and publication files present at the
measurement boundary. Missing or ambiguous measurements fail closed rather than
being interpreted as zero.

## Failure and evidence retention

Every failed check remains visible in the report. The aggregate result passes
only when every non-performance invariant passes and, in the canonical
environment, every resource ceiling passes. A local preflight may be complete
with canonical performance still pending. A material failure must be corrected
before a later scientific freeze; the seed, threshold, or fault schedule must
not be changed to make the failure disappear.
