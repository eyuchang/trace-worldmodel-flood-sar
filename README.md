# TRACE-WorldModel Flood-SAR

TRACE-WorldModel is an active TRACE architecture for auditable world models.

This repository provides the first end-to-end implementation: **Flood-SAR D0.5 Predictive Scheduling**, a dynamic rescue-planning workbench with drones, boats, ambulances, real geography, TRACE-gated scheduling, and revision.

The current verified implementation is **D0.5 Predictive Scheduling**.

## Naming note

This repository was formerly developed under the TRACE-JEPA Flood-SAR name.

The public framework name is now **TRACE-WorldModel**.

For compatibility, the Python package currently remains `trace_jepa`, and some CLI commands still use the `trace-jepa-*` prefix. These names will be migrated only after the paper and workshop release stabilize.

In this repository:

```text
TRACE-WorldModel = public framework name
Flood-SAR        = first end-to-end implementation
V-JEPA / AdaJEPA = optional future learned-world-model plug-ins
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

Learned latent prediction is optional future work behind the same world-model service boundary.

## Current release

- Current implementation: **D0.5**
- Baseline tag: `v2-baseline-d05`
- Main branch: `main`
- Development branch: `v2-fleet-map`
- Primary workbench: D0.5 browser interface
- Geography: OpenStreetMap-derived road and waterway graphs

## Requirements

- macOS or Linux
- Python 3.12
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
python -m pip install -e ".[ui,dev]"
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
├── configs/                 scenario, model, policy, and strategy settings
├── data/                    geography, manifests, and generated data
├── docs/                    mission brief, tutorials, and instructor notes
├── labs/                    student laboratory exercises
├── models/                  model manifests and optional external weights
├── scripts/                 setup, geography, and workbench commands
├── src/trace_jepa/
│   ├── contracts/           evidence, claims, actions, outcomes
│   ├── runtime/             TRACE repository, ledger, and gate
│   ├── planning/            candidate plans and repair
│   ├── predictor/           world-model and action prediction interfaces
│   ├── scenario/            Flood Environment
│   └── workbench/           D0.1–D0.5 browser workbenches
├── tests/                   unit, integration, and acceptance tests
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
- `src/trace_jepa/planning/`
- `src/trace_jepa/predictor/`

## Testing

Run all tests:

```bash
python -m pytest -q
```

Run installation verification:

```bash
trace-jepa-verify
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

## Optional learned world-model extension

TRACE-WorldModel does not require a learned latent model to run the current Flood-SAR D0.5 workbench.

The D0.5 release uses a transparent simulator and graph-based mission model so that students can inspect every state transition.

Future extensions may attach learned latent predictors, including V-JEPA or AdaJEPA-style modules, behind the same world-model service boundary.

Optional install, if the learned-model extension is enabled:

```bash
python -m pip install -e ".[jepa]"
```

Optional model download, if configured:

```bash
trace-jepa-download --model vjepa2_1_vit_base_384
```

V-JEPA is not treated as a complete rescue simulator. It may provide learned visual representations or latent predictions, but TRACE remains responsible for evidence validation, gating, revision, and authority separation.

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
