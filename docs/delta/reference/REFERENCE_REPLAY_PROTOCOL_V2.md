# WF-DFLD-01-REFERENCE replay protocol v2

Status: development implementation contract; not validation evidence.

## Purpose

The full 96-hour event chain includes every controller-visible G3 handoff. At
Reference scale, its canonical JSON representation is approximately 685 MB
because each immutable handoff carries the complete proposal catalog needed to
reproduce the decision. The public event projection has similar size. Keeping
either projection as one in-memory, uncompressed JSON artifact violates the
registered per-artifact bound and creates avoidable memory pressure.

Replay manifest v2 therefore stores `full_event_chain` and
`public_event_projection` as deterministic `canonical-json-gzip-v1` artifacts.
All other artifacts remain uncompressed canonical JSON.

## Encoding contract

For `canonical-json-gzip-v1`:

1. Each Pydantic model is dumped in JSON mode.
2. Each model is encoded with sorted keys, compact separators, ASCII escaping,
   and rejection of non-finite numbers.
3. Models are streamed, in their registered order, into one JSON array followed
   by one newline.
4. The array is compressed with gzip level 9, an empty original filename, and
   `mtime=0`.
5. The compressed bytes, byte length, SHA-256 digest, and encoding identifier
   are bound in the replay manifest.

The exact Reference environment remains part of the scientific input boundary,
including the Python and compression-library implementation used to reproduce
the registered bytes. Exact replay compares the compressed files byte for byte.

## Bounds and security

- Maximum compressed bytes per artifact: 192 MiB.
- Maximum registered artifact bytes per bundle: 512 MiB.
- Writing uses a temporary regular file in the trusted output directory,
  flushes and synchronizes it, checks the compressed bound, then atomically
  replaces the destination.
- Unsafe destinations, symlink boundaries, non-model sequence values, digest
  mismatches, and oversized artifacts fail closed.

The book/development seed measured 146,827,400 bytes for the complete compressed
event chain and 146,636,476 bytes for the compressed public projection. The
complete registered artifact inventory measured 399,434,252 bytes. These are
development engineering measurements, not scientific evaluation results.

## Scientific noninterference

This amendment changes only artifact serialization and replay-manifest schema.
It does not change scenario generation, truth, observations, policy,
reconciliation, predictor inputs, TRACE decisions, event ordering, event
digests, commitments, outcomes, or any validation estimand.
