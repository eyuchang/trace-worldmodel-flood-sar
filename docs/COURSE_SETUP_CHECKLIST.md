# Course Setup Checklist

## Before class

- [ ] Confirm students have read `docs/MISSION_BRIEF.md`.
- [ ] Verify the core package installs without PyTorch.
- [ ] Run `trace-jepa-visualize` and inspect all three SVGs.
- [ ] Run `trace-jepa-demo` and confirm the north dispatch is held.
- [ ] Confirm `summary.json` prints predicted success, claim confidence, support, OOD, actor, route, destination, and authorizing record.
- [ ] Run the full test suite.

## macOS Apple Silicon

- [ ] `uname -m` reports `arm64`.
- [ ] `conda info | grep platform` reports `osx-arm64`.
- [ ] The course environment uses Python 3.12.
- [ ] No NVIDIA GPU is required for Labs 1 and 2.

## JEPA lab

- [ ] Validate the optional PyTorch installation on the intended hardware.
- [ ] Download the checkpoint once before class.
- [ ] Record the checkpoint hash and upstream code revision.
- [ ] Prepare an institution-approved cache if classroom internet is unreliable.
- [ ] Test the feature encoder on one licensed clip.

## Data and ethics

- [ ] Use synthetic, licensed, controlled-exercise, or non-identifiable footage.
- [ ] Store provenance and license manifests.
- [ ] Do not give the teaching system autonomous emergency-dispatch authority.
