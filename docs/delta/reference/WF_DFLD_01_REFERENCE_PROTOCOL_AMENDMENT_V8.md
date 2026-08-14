# WF-DFLD-01-REFERENCE protocol amendment V8

Status: CI-orchestration correction; protected studies remain unopened.

This amendment records a source-bound correction to branch CI after three
unsuccessful workflow runs. It changes neither the Reference simulator,
scientific coefficients, estimands, registered 900-second runtime gate, nor
protected seed namespaces.

## Observed CI history

- Run `31770344929` stopped at Ruff formatting. Ruff named five files; no test
  or scientific execution began.
- Run `31791847888` passed environment verification, lint, formatting, and
  strict typing, then GitHub canceled the monolithic test-and-coverage step at
  the former 15-minute job limit. Its log contained no test failure.
- Run `31799598235` passed environment verification, lint, formatting, and
  strict typing. GitHub canceled the same monolithic step at the replacement
  45-minute job limit. Before cancellation, its pytest progress stream included
  a failure. Collection-order reconstruction identifies the failed node as
  `test_reference_g3_characterization_preserves_historical_benchmark_receipt`.

The identified test compared source hashes bound by an immutable historical
benchmark receipt with the current implementations. Three bound modules had
legitimately changed after that benchmark. The corrected test verifies the
immutable receipt digest, schema, lifecycle semantics, declared runtime-base
identity, and declared historical source-hash bindings. It does not require
current files to equal their historical versions or regenerate the expensive
current characterization fixture merely to validate a historical receipt. The
receipt itself remains byte-for-byte unchanged, and the test works from a clean
source archive without requiring arbitrary Git ancestor objects.

## Complete bounded CI execution

The single test process is replaced by a versioned, explicit shard registry.
The registry is verified against pytest collection before execution: its shard
union must equal the complete collected suite exactly, no node may be omitted or
assigned more than once, and registered node and test-file counts must match.
Every shard runs in a fresh pinned Python 3.11 job with the same branch-coverage
source set. CI uploads each hidden coverage data file, combines every fragment
only after all shards pass, enforces the unchanged coverage thresholds, and
then runs the scientific-input, committed-Small-replay, and full-diff gates.

The 45-minute limit now applies independently to each bounded shard. This is an
execution-orchestration change, not a relaxation of test or coverage scope. The
Reference Phase 6 canonical performance contract continues to require the
registered generate/run/replay operation to complete within 900 seconds in the
canonical environment.

## Provenance consequence

The workflow, shard registry, shard runner, this amendment, historical
lifecycle test, and workflow-completeness tests are scientific inputs. Their
new bytes require a new source commit, complete scientific-input inventory,
G3/Phase 6 regeneration, canonical execution receipt, and validation-freeze
binding before any validation authorization tag can be created.
