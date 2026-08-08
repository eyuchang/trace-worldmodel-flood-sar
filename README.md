
# TRACE-WorldModel Flood-SAR

TRACE-WorldModel is an active TRACE architecture for auditable world models.

The repository has two verified execution surfaces:

1. **D0.5 Predictive Scheduling**, the browser teaching workbench.
2. **WF-DFLD-01-SMALL**, the headless Tasks 1 and 2 Delta simulator.

## Naming note

This repository was formerly developed under the TRACE-JEPA Flood-SAR name.

The public framework name is now **TRACE-WorldModel**.

For compatibility, the Python package currently remains `trace_jepa`, and some CLI commands still use the `trace-jepa-*` prefix. These names will be migrated only after the paper and workshop release stabilize.

In this repository:

```text
TRACE-WorldModel = public framework name
Flood-SAR        = first end-to-end implementation
V-JEPA          = implemented optional adapter; no qualified Delta head
AdaJEPA         = possible future learned-world-model plug-in
trace_jepa       = temporary internal Python package name
trace-jepa-*     = temporary CLI command prefix
```


## Research papers

This repository implements the first end-to-end Flood-SAR workbench for the TRACE-WorldModel research program.

The foundational TRACE schema is described in:

- Edward Y. Chang and Emily J. Chang.  
  **TRACE: An Operational Reasoning Schema for Auditable Agentic Commitments.**  
  arXiv:2607.12480, 2026.  
  <https://arxiv.org/abs/2607.12480>

TRACE-WorldModel builds on TRACE by moving from typed reasoning records and commitment gates to an active world-model workbench: simulated or learned predictions become TRACE-gated evidence before they can affect rescue planning, dispatch, revision, or completion.

A separate TRACE-WorldModel paper is planned for the Flood-SAR implementation and evaluation.

## System overview

The workbench simulates a major flooding event in the San Francisco Bay Area and Delta waterways.

A central Mission Controller coordinates:

- reconnaissance drones;
- rescue boats;
- ambulances;
- emergency incidents;
- transfer docks;
- hospitals;
- road and waterway networks;
- changing environmental conditions.

When a 911 alert is received, the system:

1. dispatches a drone for reconnaissance;
2. verifies the callers’ location and site conditions;
3. determines whether water or ground access is appropriate;
4. evaluates urgency, risk, travel time, capacity, and uncertainty;
5. selects and dispatches suitable rescue assets;
6. coordinates boat-to-ambulance transfer when required;
7. delivers rescued people to a hospital;
8. records evidence, decisions, schedules, and outcomes through TRACE.

A pickup is not counted as a completed rescue until the people are safely delivered.

## Architecture

```text
Human Incident Commander
          |
          v
   Mission Controller
          |
          +-- Mission State
          +-- Planner
          +-- World Model
          +-- TRACE Gate
          +-- Action Dispatcher
          |
          +-- Reconnaissance Drones
          +-- Rescue Boats
          +-- Ambulances
          |
          v
   Dynamic Flood Environment
```

The architecture combines:

- **TRACE** — evidence logging, validation, decision records, timing records, revision, and audit;
- **Trivium** — causal reasoning, uncertainty analysis, and missing-evidence identification;
- **SagaLLM** — multi-step planning, resource coordination, handoffs, compensation, and repair;
- **World-model service boundary** — a common interface through which transparent simulators, graph-based predictors, learned latent models, or future JEPA/AdaJEPA modules can provide predictive evidence.

The current world model is a transparent, auditable simulator over mission state, fleet state, road and waterway graphs, transfer docks, hospitals, and dynamic incidents.

Learned prediction is optional behind the same boundary. The repository includes
governed MLP and V-JEPA-backed adapters, but no learned Delta predictor is
qualified or used by the canonical walkthrough.

## Current execution surfaces

- Current implementation: **D0.5**
- Baseline tag: `v2-baseline-d05`
- Main branch: `main`
- Primary workbench: D0.5 browser interface
- Geography: OpenStreetMap-derived road and waterway graphs
- Experimental evaluation layer: **RQ5 revalidation-guard protocol** (optional; off by default in the teaching gate)
- Delta research surface: **WF-DFLD-01-SMALL v8**, headless and deterministic
- Delta canonical predictor: transparent Toy teaching fixture
- Delta learned-predictor status: MLP and V-JEPA are **unqualified**

## Requirements and Python versions

- macOS or Linux
- Python 3.10 or later for the package
- Python 3.12 is the D0.5 workshop recommendation
- Python 3.11.14 on Linux/amd64 is the exact Delta reference environment
- Conda or Miniforge
- Git
- GitHub CLI, recommended for private repo access and release assets
- Modern web browser

## Quick start

Clone the repository:

```bash
mkdir -p "$HOME/Projects"
cd "$HOME/Projects"
gh repo clone eyuchang/trace-worldmodel-flood-sar
cd "$HOME/Projects/trace-worldmodel-flood-sar"
```

Activate the environment:

```bash
source "$HOME/miniforge3/etc/profile.d/conda.sh"
conda activate trace-jepa
```

Install the package:

```bash
python -m pip install -e ".[ui,dev,geography]"
```

Verify the installation:

```bash
trace-jepa-verify
python -m pytest -q
```

Start the D0.5 browser workbench:

```bash
./scripts/run_d05.sh
```

Open the workbench on macOS:

```bash
open "http://127.0.0.1:8030/d05"
```

## WF-DFLD-01-SMALL Delta simulator

The August WF-DFLD-01 Tasks 1 and 2 deliverable is a separate headless,
deterministic Small simulator. It uses offline simulation-grade geography
curated from authoritative government sources, latent
truth before lossy reports, the complete TRACE evidence/record/commitment path,
and one substitutable predictor protocol. Toy is the default teaching fixture;
MLP and V-JEPA-backed predictors are unqualified unless a separate frozen
qualification artifact names the exact model, calibration, and action class.

The exact Delta environment is the digest-pinned Linux/amd64 image
`python@sha256:88b6d3132a0850db3587a4f4ff28d5568e7d65ff99f0ee34f42be864ddb4ca1d`
with [`requirements-delta-python311.lock`](requirements-delta-python311.lock).
The image and complete lock are bound by the
[`python311_linux_amd64_v1.json`](data/scenario/delta/environment/python311_linux_amd64_v1.json)
contract. A local environment is convenient for development but is not the
canonical book environment unless it passes that contract exactly.

Install the frozen Delta dependencies in Python 3.11:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-delta-python311.lock
.venv/bin/python -m pip install -e . --no-deps
```

Generate and cleanly replay a fresh run:

```bash
delta_work_root="$(mktemp -d)"
.venv/bin/trace-jepa-delta-small run --output "$delta_work_root/run"
.venv/bin/trace-jepa-delta-small replay \
  --reference "$delta_work_root/run" \
  --output "$delta_work_root/replay"
```

Run the safe development study. This mode can access only the 100 declared
development seeds and cannot load the untouched holdout:

```bash
.venv/bin/trace-jepa-delta-small validate \
  --study development \
  --output "$delta_work_root/development-validation.json"
```

After the write-once v8 report and book bundle have been published, verify the
committed reference directly:

```bash
.venv/bin/trace-jepa-delta-small replay \
  --reference data/scenario/delta/reference/wf_dfld_01_small_book_v4 \
  --output "$delta_work_root/book-v4-replay"
```

Only after the verified original report exists, replicate the registered study
and regenerate publication artifacts:

```bash
.venv/bin/trace-jepa-delta-small validate \
  --study replication \
  --original-report docs/delta/validation/WF_DFLD_01_SMALL_VALIDATION_V4.json \
  --output "$delta_work_root/validation-replication.json"
.venv/bin/trace-jepa-delta-small publish \
  --reference data/scenario/delta/reference/wf_dfld_01_small_book_v4 \
  --output "$delta_work_root/book-v4-figures"
```

The original `confirmatory-v7` execution is not exposed as a local reproduction
command. It requires the dedicated, manually authorized remote workflow, the
exact pushed preregistration commit, the complete scientific-input manifest,
and the digest-pinned environment. The earliest successful authorized workflow
is the original; every later execution is labeled replication. Until that
workflow runs, no v8 confirmatory result is claimed.

The primary v8 operational-load measure is strict one-resource/one-incident
concurrency. The v6 value of 1.5 is retained only as the historical
`registered_normalized_coverable_load_index`; it is not relabeled as conventional
demand/capacity. V8 reports strict, uncapped compatible-service-unit, and
historical normalized measures together and has no post-hoc strict-ratio gate.
Services scheduled beyond the six-hour window remain busy and are reported as
`active_at_scenario_censoring`, never as completed.

V8 reconciliation uses a reversible controller-visible evidence graph. Hard
revision/callback links may confirm a relationship; ambiguous soft evidence is
retained as `suspected` without merging or suppressing dispatch. The canonical
`evidence-graph-q075` rule was selected on development seeds only. Its paired
comparison with the immutable old heuristic is preregistered for the untouched
holdout; no improvement claim is made before that comparison succeeds.

The common predictor seam includes a real content-addressed V-JEPA adapter and a
separate flood-head loader. Heavyweight official-checkpoint encoding is optional
and offline; it is not a qualification study. Run the small project-owned fixture:

```bash
.venv/bin/python -m pytest -q tests/test_vjepa_adapter.py
```

Download an official checkpoint only as an explicit optional action. The
immutable pin is input and the mutable receipt is a separate output:

```bash
.venv/bin/trace-jepa-download \
  --pin-manifest models/manifests/vjepa2_1_vit_base_384.manifest.json \
  --receipt models/receipts/vjepa2_1_vit_base_384.download.json \
  --checkpoint-dir models/external/vjepa2
```

No learned Delta predictor is qualified. Without an exact frozen qualification
artifact, MLP and V-JEPA evidence fails closed and high-consequence actions HOLD.

Delta documentation:

- [Frozen v8 methodology](docs/delta/WF_DFLD_01_SMALL.md)
- [V8 remediation protocol](docs/delta/WF_DFLD_01_SMALL_V8_PROTOCOL.md)
- [Superseded unexecuted v7 protocol](docs/delta/WF_DFLD_01_SMALL_V7_PROTOCOL.md)
- [Geography data card](docs/delta/GEOGRAPHY_DATA_CARD.md)
- [Reduced-order hydrology model card](docs/delta/HYDROLOGY_MODEL_CARD.md)
- [Observation, reconciliation, and capacity protocol](docs/delta/OBSERVATION_AND_CAPACITY_PROTOCOL.md)
- [Predictor qualification table](docs/delta/PREDICTOR_QUALIFICATION.md)
- [V2 amendment and retained history](docs/delta/WF_DFLD_01_SMALL_V2_AMENDMENT.md)
- [Scientific-input manifest](data/scenario/delta/provenance/v8_scientific_input_manifest_v1.json)
- [Process calibration report](data/scenario/delta/calibration/v8_process_coefficients_v1.json)
- [Reconciliation selection report](data/scenario/delta/calibration/v8_reconciliation_selection_v1.json)
- V8 acceptance protocol: `configs/scenarios/wf_dfld_01_small_acceptance_v4.yaml` after preregistration
- V8 validation report: `docs/delta/validation/WF_DFLD_01_SMALL_VALIDATION_V4.json` after the once-only run
- V8 reference bundle: `data/scenario/delta/reference/wf_dfld_01_small_book_v4` after publication
- V8 figures: `docs/delta/figures/wf_dfld_01_small_v4` after publication

Every v8 numerical statement published after the holdout must be generated from
the v4 book bundle's machine-readable publication table. Small uses a synthetic,
nonrepresentative cohort; simulation-grade geography; reduced-order uncalibrated
hydrology; and a frozen preauthorized-automatic-aid teaching assumption. It is
not historically or demographically calibrated, does not establish operational
readiness, and excludes Task 3 breach, cascade, negotiated mutual aid, crew
rotation, federation, casualty, full-network, and UI mechanisms.

Or open this address manually:

```text
http://127.0.0.1:8030/d05
```

## Student installation guide

Workshop participants should complete the detailed macOS setup before Day 3:

- [Student Setup and Clone Guide for macOS](docs/STUDENT_SETUP_MAC.md)

## Geography data

Two large generated geography files are intentionally excluded from normal Git history:

```text
data/geography/antioch_delta_real_v1/roads.geojson
data/geography/antioch_delta_real_v1/road_graph.json
```

They are distributed separately through GitHub Releases:

<https://github.com/eyuchang/trace-worldmodel-flood-sar/releases>
```text
https://github.com/eyuchang/trace-worldmodel-flood-sar/releases
```

Expected release assets:

```text
antioch_delta_real_v1.tar.gz
antioch_delta_real_v1.tar.gz.sha256
```

Download the geography assets:

```bash
mkdir -p "$HOME/Downloads/trace-jepa-assets"

gh release download v0.5-workshop \
  --repo eyuchang/trace-worldmodel-flood-sar \
  --pattern "antioch_delta_real_v1.tar.gz*" \
  --dir "$HOME/Downloads/trace-jepa-assets"
```

Verify the checksum:

```bash
cd "$HOME/Downloads/trace-jepa-assets"
shasum -a 256 -c antioch_delta_real_v1.tar.gz.sha256
```

Expected result:

```text
antioch_delta_real_v1.tar.gz: OK
```

After downloading the archive, extract it from the repository root:

```bash
cd "$HOME/Projects/trace-worldmodel-flood-sar"

tar -xzf "$HOME/Downloads/trace-jepa-assets/antioch_delta_real_v1.tar.gz" \
  -C data/geography
```

Verify that the two files are present:

```bash
ls -lh \
  data/geography/antioch_delta_real_v1/roads.geojson \
  data/geography/antioch_delta_real_v1/road_graph.json
```

## D0.1–D0.5 development lineage

### D0.1 — TRACE contracts and evidence logging

D0.1 introduces:

- structured evidence objects;
- typed claims;
- proposed actions;
- clear, hold, defer, and reject decisions;
- append-only revisions;
- TRACE hash-chain validation.

### D0.2 — Graph-constrained navigation

D0.2 ensures that:

- boats move on waterway graph edges;
- ambulances move on road graph edges;
- displayed routes correspond to executed movement;
- rescue means safe delivery, not merely pickup.

### D0.3 — Multi-asset coordination

D0.3 adds:

- multiple drones;
- multiple boats;
- multiple ambulances;
- multiple incidents;
- resource assignment;
- urgency-based prioritization;
- preemption and replanning.

### D0.4 — Real geography

D0.4 introduces:

- OpenStreetMap-derived roads and waterways;
- real longitude and latitude coordinates;
- facilities and transfer docks;
- cached graph and GeoJSON assets;
- geographically constrained routing.

### D0.5 — Predictive scheduling

D0.5 adds:

- reconnaissance-first planning;
- parallel response preparation;
- dynamic transfer-dock selection;
- early ambulance dispatch;
- capacity-aware scheduling;
- route- and timing-aware coordination;
- TRACE schedule commitments;
- boat-to-ambulance handoffs;
- hospital delivery;
- completed-alert cleanup;
- corrected fleet icon anchoring.

### Experimental — RQ5 revalidation guard

Beyond the D0.5 workbench, the repository includes an experimental-profile extension path for campaign evaluation.

Predictor-version provenance attaches optionally to world-model evidence without changing the teaching baseline schema:

- `predictor_version`
- `calibration_version`
- `prediction_timestamp`
- `claim_family`
- `adequacy_status`

The TRACE gate can enable a Section 5.5 revalidation guard with two named checks:

- `model_version_current`
- `calibration_adequate_for_class`

When the guard is enabled, high-consequence commitments cannot CLEAR on a superseded or unqualified predictor version; they HOLD pending revalidation or calibration qualification.

RQ5 is pre-registered before held-out runs under the same freeze discipline as RQ1–RQ4:

```bash
python scripts/register_rq5_protocol.py
```

Protocol declaration: [`configs/protocols/rq5_revalidation_guard.yaml`](configs/protocols/rq5_revalidation_guard.yaml).

Guard-enabled policy: [`configs/policies/trace_rq5_guard_v1.yaml`](configs/policies/trace_rq5_guard_v1.yaml).

Declared RQ5 structure:

- scenarios: control; mid-mission predictor-version replacement with an initially unqualified successor;
- arms: gate with and without the revalidation guard;
- measures: bad-version CLEAR count, holds pending revalidation, time to restored operation, verification cost, mission completion, rescued people, and store replayability;
- invariant: under the guard, no high-consequence CLEAR on a superseded or unqualified model version.

Appendix B formal-extension checks (closed-form deadline, censored cost identity, scheduler separation, sub-tick Zeno HOLD) live under `src/trace_jepa/experimental/formal/`.

## D0.5 rescue lifecycle

```text
911 alert
   |
   v
Drone reconnaissance
   |
   v
Location and access verification
   |
   v
Response preparation
   |
   v
Boat or ground dispatch
   |
   v
Rescue pickup
   |
   v
Transfer dock
   |
   v
Ambulance handoff
   |
   v
Hospital delivery
   |
   v
TRACE completion record
```

## Dynamic controls

The browser workbench includes controls for five classes of dynamic situations.

### S1 — Uncertainty

- sensor noise;
- confidence;
- out-of-distribution score;
- missing evidence.

### S2 — Dynamics

- river level;
- road congestion;
- waterway availability;
- route opening and closure.

### S3 — Joint reasoning and isolation

- shared planning;
- coordinated resource assignment;
- evidence provenance;
- isolation of invalid or stale information.

### S4 — Shocks

- drone failure;
- boat failure;
- route closure;
- sudden escalation;
- resource outage.

### S5 — Reconnaissance

- drone evidence collection;
- information-gathering actions;
- missing-evidence resolution;
- verification before commitment.

## Tunable parameters

Workshop participants can vary:

- number of drones;
- number of boats;
- number of ambulances;
- boat capacity;
- ambulance capacity;
- incident severity;
- number of stranded people;
- sensor uncertainty;
- preemption threshold;
- river conditions;
- traffic conditions;
- planning and strategy weights.

## Strategy injection

Advanced exercises can compare different planning strategies, including:

- fastest expected rescue;
- lowest-risk rescue;
- maximum number of people delivered;
- severity-prioritized rescue;
- preservation of scarce boats;
- minimum ambulance waiting time.

Strategy choices should be reflected in TRACE records so that changes in planning behavior remain auditable.

## Mission invariant

The system aims to preserve the following accounting invariant:

```text
people waiting
+ people onboard rescue assets
+ people at transfer locations
+ people in ambulances
+ people delivered
=
total people accounted for
```

No person should silently disappear from mission state.

## TRACE record flow

A consequential action should include:

```text
trigger
→ evidence
→ claim
→ proposed action
→ predicted consequence
→ TRACE gate decision
→ committed command
→ observed outcome
→ revision or completion
```

TRACE is intended to make planning decisions inspectable, revisable, and auditable.

## Project layout

```text
trace-worldmodel-flood-sar/
├── configs/
│   ├── policies/            TRACE gate thresholds (baseline and RQ5 guard)
│   ├── protocols/           pre-registered campaign protocols (RQ5)
│   ├── scenarios/           frozen Delta scenario and acceptance contracts
│   └── experimental/        experimental-profile bootstrap settings
├── data/
│   ├── geography/           D0.4 workbench geography
│   └── scenario/delta/      Delta sources, catalogs, calibration, references
├── docs/
│   ├── delta/               Delta methods, cards, validation, and figures
│   └── ...                  mission brief, tutorials, and instructor notes
├── labs/                    student laboratory exercises
├── models/                  model manifests and optional external weights
├── scripts/                 setup, geography, workbench, and protocol registration
├── src/trace_jepa/
│   ├── contracts/           evidence, claims, actions, outcomes
│   ├── experimental/        RQ5 profile, revalidation guard, formal checks
│   ├── runtime/             TRACE repository, ledger, and gate
│   ├── planning/            candidate plans and repair
│   ├── predictor/           world-model and action prediction interfaces
│   ├── scenario/delta/      WF-DFLD-01 generator, TRACE runner, evaluation
│   ├── scenario/            other Flood Environment components
│   └── workbench/           D0.1–D0.5 browser workbenches
├── tests/                   unit, integration, acceptance, and RQ5 contract tests
└── third_party/             optional external dependencies
```

The repository name has changed to `trace-worldmodel-flood-sar`. The internal package path remains `src/trace_jepa/` for compatibility.

## Important documentation

Begin with:

- [`docs/MISSION_BRIEF.md`](docs/MISSION_BRIEF.md)
- [`docs/TRACE_RECORD_WALKTHROUGH.md`](docs/TRACE_RECORD_WALKTHROUGH.md)
- [`docs/DYNAMIC_WORKBENCH.md`](docs/DYNAMIC_WORKBENCH.md)
- [`docs/D04_STEP3_COMPLETE_FILES.md`](docs/D04_STEP3_COMPLETE_FILES.md)
- [`docs/D05_PREDICTIVE_SCHEDULING.md`](docs/D05_PREDICTIVE_SCHEDULING.md)
- [`docs/STUDENT_TUTORIAL.md`](docs/STUDENT_TUTORIAL.md)
- [Student Setup and Clone Guide for macOS](docs/STUDENT_SETUP_MAC.md)

## Important source files

- `src/trace_jepa/workbench/d05_server.py`
- `src/trace_jepa/workbench/d05_static/index.html`
- `src/trace_jepa/workbench/network_pose.py`
- `src/trace_jepa/workbench/geography_builder.py`
- `src/trace_jepa/controller.py`
- `src/trace_jepa/runtime/`
- `src/trace_jepa/experimental/`
- `src/trace_jepa/planning/`
- `src/trace_jepa/predictor/`
- `configs/protocols/rq5_revalidation_guard.yaml`
- `configs/policies/trace_rq5_guard_v1.yaml`
- `scripts/register_rq5_protocol.py`

## Testing

Run all tests:

```bash
python -m pytest -q
```

Run installation verification:

```bash
trace-jepa-verify
```

RQ5 contract and formal-regime tests:

```bash
python -m pytest -q \
  tests/test_experimental_profile_provenance.py \
  tests/test_revalidation_guard.py \
  tests/test_rq5_protocol.py \
  tests/test_formal_regime.py
```

Register the RQ5 protocol before any held-out campaign run:

```bash
python scripts/register_rq5_protocol.py
```

The D0.5 workbench should also be tested manually by completing at least one full rescue lifecycle.

## Workshop use

This repository supports the Day 3 code laboratory associated with *The Path to AGI*, Volumes 1 and 2.

Students should:

1. install and verify the environment;
2. run the baseline rescue scenario;
3. inspect TRACE records;
4. modify fleet and environment parameters;
5. compare planning strategies;
6. introduce a disruption;
7. observe repair or replanning;
8. record a short end-to-end demonstration.

## Earlier deterministic tutorial

The repository also retains the earlier deterministic TRACE tutorial centered on the Riverside Apartments scenario.

That tutorial demonstrates:

- unsupported high-confidence model predictions;
- low-support and high-OOD evidence;
- holding irreversible actions;
- reversible drone verification;
- append-only revision;
- local replanning;
- final authorization;
- provenance between a TRACE version and a dispatched command.

See:

- [`docs/EIGHT_STEP_IMPLEMENTATION.md`](docs/EIGHT_STEP_IMPLEMENTATION.md)
- `docs/eight_step_deck/`
- [`docs/TRACE_RECORD_WALKTHROUGH.md`](docs/TRACE_RECORD_WALKTHROUGH.md)

These materials remain useful for teaching the core TRACE accountability path.

## Optional learned world-model execution

TRACE-WorldModel does not require a learned latent model to run either verified
surface. D0.5 and the canonical Delta walkthrough use transparent models.

The D0.5 release uses a transparent simulator and graph-based mission model so that students can inspect every state transition.

The repository implements MLP and V-JEPA-backed adapters behind the same
action-prefix predictor boundary. Their presence establishes interface,
provenance, fail-closed loading, substitution, and revalidation behavior—not
Delta prediction effectiveness.

Optional install, if the learned-model extension is enabled:

```bash
python -m pip install -e ".[jepa]"
```

Optional model download, if configured:

```bash
trace-jepa-download \
  --pin-manifest models/manifests/vjepa2_1_vit_base_384.manifest.json \
  --receipt models/receipts/vjepa2_1_vit_base_384.download.json \
  --checkpoint-dir models/external/vjepa2
```

V-JEPA is not treated as a complete rescue simulator. The pinned encoder may
provide content-addressed visual features to a separately versioned flood head,
but no learned head is qualified in this repository. TRACE remains responsible
for evidence validation, gating, revision, and authority separation.

The target extension architecture is:

```text
learned visual encoder, such as V-JEPA
+ flood-state fusion
+ action-conditioned predictor
+ calibrated semantic probes
+ TRACE runtime
+ human authority boundary
```

## Research and safety scope

This repository is an educational simulator and research prototype.

It is not certified for:

- real emergency response;
- autonomous vehicle control;
- medical decision-making;
- public-safety deployment;
- operational military or defense deployment.

All consequential actions must remain subject to qualified human authorization and domain-specific validation.

## Author

Developed by Professor Edward Chang at Stanford University as part of the TRACE-WorldModel and *The Path to AGI* research and teaching program.
