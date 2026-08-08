# ADR 0001: Cohesive boundaries for WF-DFLD-01-SMALL

- Status: Accepted
- Date: 2026-08-08
- Scope: Tasks 1 and 2 canonical implementation

## Context

The initial Small implementation grew in a flat package. Large model, runner,
artifact, population, validation, and publication modules mixed typed contracts,
scientific mechanics, orchestration, compatibility code, and historical
verification. That organization made otherwise correct code harder to review and
made cross-layer dependencies easy to introduce accidentally.

The scientific requirement is stronger than ordinary modularity: hidden truth
must remain outside online reconciliation; registered calculations must not
silently depend on legacy code; and historical artifacts must remain verifiable
after the canonical implementation evolves.

## Decision

The canonical Delta package is divided into `domain`, `geography`, `generation`,
`reconciliation`, `runtime`, `provenance`, `validation`, `publication`, and
`legacy` subpackages.

Dependency direction is enforced by tests:

- `domain` depends on no higher layer.
- generation and geography may depend on domain and shared support.
- reconciliation consumes only controller-visible observation/domain contracts.
- runtime may depend on domain, generation outputs, reconciliation, predictor,
  and TRACE contracts.
- provenance, validation, and publication may consume lower-layer outputs but
  may not become simulator dependencies.
- legacy implementations are reached only by explicit historical-verification
  paths.

Stable entry points remain `generate_delta_small`, `execute_delta_small`,
`run_delta_small`, `verify_exact_replay`, and the public predictor exports. Thin
facades retain former flat import paths for one compatibility release.

The architecture is evaluated by cohesion and dependency direction, not an
arbitrary line-count limit. Complexity is limited to 12, branches to 12,
statements to 50, and ordinary arguments to six unless a typed request object is
used.

## Consequences

- Scientific mechanisms can be reviewed independently from artifact and figure
  code.
- Hidden-lineage exclusions have a structural boundary in addition to tests.
- Historical algorithms remain auditable without driving new simulations.
- Some compatibility facades temporarily duplicate import surfaces; they are
  intentionally thin and must be removed in a later major revision.
- Byte-equivalence and import-closure tests are required whenever modules move.
