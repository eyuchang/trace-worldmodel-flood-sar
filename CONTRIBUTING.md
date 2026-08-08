# Contributing to TRACE-WorldModel Flood-SAR

This repository contains both teaching software and preregistered research
software. Changes to WF-DFLD-01-SMALL must preserve scientific auditability as
well as ordinary software quality.

## Scientific-change protocol

Before changing simulator mechanics, metrics, coefficients, evaluation rules,
or data:

1. State the scientific reason and the affected causal mechanism.
2. Decide whether the change creates a new protocol revision.
3. Preserve prior configurations, reports, and reference bundles as immutable
   evidence; never rewrite an adverse result.
4. Use development seeds only while implementing or selecting a method.
5. Freeze code, inputs, environment, gates, and the scientific-input manifest
   before deriving a new holdout list.
6. Never execute an untouched confirmatory ensemble locally.
7. Publish a failed original confirmation without retuning, replacing seeds, or
   declaring a second primary holdout.

The book seed is descriptive. It must not be tuned or treated as confirmatory
evidence.

## Delta package boundaries

Canonical Task 1/2 code follows this dependency direction:

```text
domain <- geography / generation <- runtime <- provenance / validation / publication
                         ^              |
                         + reconciliation
```

- `domain`: frozen typed contracts only; no generation or runtime imports.
- `geography`: source models, deterministic derivation, and secure offline build.
- `generation`: physical state, exposure, incidents, observations, resources,
  coordination, and priors.
- `reconciliation`: controller-visible evidence and belief-cluster transitions;
  hidden lineage is forbidden.
- `runtime`: routing, predictor evidence, capacity, TRACE execution, outcomes.
- `provenance`: canonical artifacts, environment, replay, scientific manifests.
- `validation`: typed statistics, registered studies, and report verification.
- `publication`: deterministic, metadata-free figures and result tables.
- `legacy`: immutable historical algorithms required to verify prior evidence.

Compatibility modules at the former flat import paths may re-export public APIs
for one release. Canonical modules must not import those facades or private names
from another module.

## Security and data handling

- All runtime and CI inputs are offline.
- Learned-model files, feature caches, qualifications, geography archives, pins,
  and receipts require a caller-supplied trusted root.
- Reject path traversal, symlinks, non-regular files, oversized artifacts,
  malformed archives, unexpected arrays, and digest mismatches.
- Use canonical JSON and atomic file replacement for research artifacts.
- Do not commit real callback information, residential addresses, unrestricted
  third-party data, model weights, secrets, or personal data.
- Hidden truth and lineage may be used only for offline evaluation and must never
  enter predictor requests, controller decisions, TRACE artifacts, or public
  knowledge-state figures.

## Quality checks

Install the development and geography dependencies, then run:

```bash
python -m ruff check src/trace_jepa/scenario/delta src/trace_jepa/predictor src/trace_jepa/support tests/delta tests/predictor
python -m ruff format --check src/trace_jepa/scenario/delta src/trace_jepa/predictor src/trace_jepa/support tests/delta tests/predictor
python -m mypy src/trace_jepa/scenario/delta src/trace_jepa/predictor src/trace_jepa/experimental/revalidation.py src/trace_jepa/support
python -m pytest
python -m pytest --cov=trace_jepa.scenario.delta --cov=trace_jepa.predictor --cov=trace_jepa.experimental.revalidation --cov=trace_jepa.support --cov-branch --cov-report=json:coverage-delta.json
python scripts/check_delta_coverage.py coverage-delta.json
git diff --check
```

The reviewed high-consequence Task 1/2 surface must remain at or above 90%
line coverage and 85% branch coverage. The complete measured surface is printed
as an additional transparent diagnostic.

## Commits and external actions

- Keep protocol, architecture, mechanics, validation, data, and documentation
  changes reviewable as separate passing commits.
- Include the relevant tests with each substantive change.
- Do not mix Task 3, UI, or workbench architecture changes into the Delta
  preregistration branch.
- Branch push, authorization-tag push, and original-result push are separate
  permission gates.
- Never open a pull request or modify `main` without explicit authorization.

The confirmatory authorization design is recorded in
[`docs/adr/0002-tag-authorized-original-confirmation.md`](docs/adr/0002-tag-authorized-original-confirmation.md).
