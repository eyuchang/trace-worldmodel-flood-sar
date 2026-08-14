# ADR: Private seed-plan recovery for Reference validation-v2

Status: accepted locally; remote execution requires a separately approved tag
Decision date: 2026-08-14

## Context

The original workflow transferred a raw protected seed plan from an offline
root container to a GitHub artifact. Its atomic writer correctly used a
restrictive file mode, but container and runner ownership differed. Upload
failed before any mission ran. Making that file world-readable would address
the immediate symptom while retaining an unnecessary pre-evaluation artifact
and a wider disclosure surface.

## Decision

Use deterministic private rederivation instead of transferring the raw plan
between jobs.

1. Authorization verifies the frozen base science, recovery governance, exact
   failed original lifecycle, and absence of a prior recovery attempt. It does
   not derive seeds.
2. Each shard rederives the exact validation-v2 plan only inside its ephemeral,
   network-disabled container. It checks the preregistered digest and retains
   only its five in-memory seed values long enough to execute its assigned
   missions.
3. Shards upload only mission receipts containing one-way seed digests, not
   seed values.
4. Aggregation rederives privately, verifies receipt-to-seed bindings, and
   writes the complete report. The raw plan becomes eligible for disclosure
   only after the complete report has been written successfully.
5. All bind-mounted output is written as the runner UID/GID with restrictive
   permissions and verified before upload.

## Consequences

- The protected list is never a pre-evaluation GitHub artifact.
- Shards remain independently reproducible and bind to one exact list digest.
- The base scientific freeze is unchanged; a separate recovery manifest binds
  the orchestration amendment and the immutable base evidence.
- Recovery must carry a distinct identity and cannot silently replace the
  failed authorization run.
- If infrastructure interrupts mission execution, continuation is limited to
  missing shards under a new authorization. It is not a general workflow
  rerun.
- Recovery reuses the immutable base mission runner and adverse-receipt factory
  through one hash-bound compatibility adapter. The recovery layer implements
  the already frozen aggregate-gate formula locally and tests it against the
  registered gate semantics, avoiding another private cross-package dependency.
- Recovery code is separated into protected-plan, shard, interruption,
  aggregation, binding, and authorization modules. A thin execution facade
  preserves the recovery command surface without concentrating these concerns
  in one large orchestrator.

## Rejected alternatives

- **Reuse or move the original tag:** this would erase the authorization
  lifecycle and contradict the attempt-one guard.
- **Use workflow run attempt two:** the frozen original explicitly rejects it,
  and the old workflow would reproduce the ownership defect.
- **Create a new seed namespace:** this would introduce avoidable
  seed-selection flexibility after the original namespace had been derived.
- **Change the plan to mode `0644`:** this fixes readability by broadening
  exposure and leaves the unnecessary intermediate artifact in place.
- **Rerun all shards after a partial interruption:** completed outcomes would
  already be observed; only missing mission indices may be continued.
