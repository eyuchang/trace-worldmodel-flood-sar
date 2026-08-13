"""Registered byte limits for Reference replay artifacts."""

# The compressed, complete 96-hour event chain is approximately 140 MiB at
# Reference scale. The per-artifact ceiling permits bounded headroom while the
# independent bundle ceiling prevents aggregate growth from going unnoticed.
REFERENCE_ARTIFACT_MAX_BYTES = 192 * 1024 * 1024
REFERENCE_BUNDLE_MAX_BYTES = 512 * 1024 * 1024
