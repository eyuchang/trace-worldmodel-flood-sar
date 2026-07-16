# TRACE-JEPA Dynamic Flood-SAR Workbench (D0.2)

This release is the first executable shell for the S1-S5 research program in Chapter 9.
It is a research simulator, not a live emergency-dispatch system.

## What is operational now

- event-sourced simulation state;
- separate hidden `TruthState` and Mission Controller `ControllerState`;
- append-only, hash-chained simulation event log;
- existing append-only TRACE evidence, record, and commitment stores;
- real-time FastAPI/WebSocket backend;
- browser UI with play, pause, step, reset, speed, and manual planning controls;
- controller, ground-truth, and difference map views;
- live agent/group/route visualization;
- complete boat pickup, evacuation, safe-handoff, and standby lifecycle;
- asset-specific animated SVG drone and boat glyphs;
- explicit same-incident alert count semantics and UI feedback;
- latest TRACE records, event timeline, and statistics;
- live S1-S5 controls, each entering the simulator as a typed `SimulationEvent`;
- deterministic replay from the event log;
- 33 passing tests across the original scaffold and dynamic workbench.

The world model is currently a transparent **surrogate predictor**. It computes success,
hazard, support, OOD, uncertainty, arrival time, and resource margin from the controller-visible
state. It is not V-JEPA. The controller/model boundary is retained so a later GPU model service
can replace the surrogate without changing the UI, event log, TRACE runtime, or commitment
contracts.

## Install and run on the course Mac

```bash
source "$HOME/miniforge3/etc/profile.d/conda.sh"
conda activate trace-jepa

cd "$HOME/Projects/trace_jepa_dynamic_workbench"
python -m pip install -e ".[ui,dev]"
pytest
trace-jepa-ui --host 127.0.0.1 --port 8000
```

Open another terminal or use Finder:

```bash
open http://127.0.0.1:8000
```

## UI regions

1. **Top toolbar**: start, pause, single-step, force a planning cycle, reset, speed, commander authority, export.
2. **S1-S5 controls**: every change becomes an immutable input event.
3. **Operational map**: routes, water, groups, moving assets, planned paths, and knowledge/truth differences.
4. **Mission statistics**: rescue, gate, revision, uncertainty, water, and integrity metrics.
5. **TRACE inspector**: latest records with verdict, consumer decision, failed gates, and claim.
6. **Event timeline**: the ordered event source from which the dynamic state is replayed.

## Rescue lifecycle

Arrival at the incident is not recorded as rescue completion. A boat first boards the waiting
people, then the Mission Controller creates a fresh `evacuate_to_safety` candidate. That return
leg receives its own prediction, TRACE record, authority check, and graph-valid waterway path.
People count as rescued only after unloading at the declared Safe Transfer Dock. The boat then
enters standby at the safe dock, ready for a later assignment. In the Riverside scenario, the
safe dock is co-located with the Rescue Base.

The map shows waiting people at the incident, onboard people on the boat badge, delivered people
at the safe dock, and a completed marker at the original incident site.

The emergency-call form also requires the user to say whether a repeated number is the current
total still waiting or additional people at the same incident. The API returns the resulting
waiting, onboard, delivered, and alert counts so the UI cannot silently retain a stale `4`.

## S1-S5 controls

### S1 uncertainty

- drone report accuracy;
- sensor noise;
- observation latency;
- packet loss;
- OOD severity;
- random seed.

These parameters change the sensor report generated after a reconnaissance action and the
surrogate model's support, OOD, and uncertainty values.

### S2 dynamics

- rain intensity;
- upstream inflow;
- water-rise rate;
- route-closure depth;
- clearance horizon;
- observation freshness.

Water evolves on every simulation tick. Routes change truth status when water or debris makes
them impassable. TRACE evaluates observation age and the controller can no longer treat a
clearance as timeless.

### S3 joint reasoning

- mission budget and objective weights;
- add stranded groups at arbitrary map coordinates;
- add drones, boats, helicopters, or ground teams;
- set capacity, speed, resource state, and weather tolerance.

The planner refuses to use an already assigned asset for a second group. The test suite asserts
zero double commitment under repeated planning cycles.

### S4 shocks

The UI can inject:

- communication loss/restore;
- sensor degradation;
- levee breach;
- route submergence;
- wind shift;
- group deterioration;
- asset grounding;
- fuel/resource limitation.

The button emits `INJECT_SHOCK`; it never mutates a simulator object directly.

### S5 reconnaissance

- drone endurance;
- sensor quality;
- sector weather;
- value-of-information weight;
- explicit route survey requests.

An operator-requested survey takes precedence among admissible reconnaissance candidates. Each
sortie still receives a TRACE record and cannot bypass its own safety and support gates.

## Event path

```text
browser control
    -> POST /api/events
    -> immutable SimulationEvent
    -> hash-chained EventStore
    -> single reducer
    -> TruthState / ControllerState
    -> planner + surrogate prediction
    -> WorldModelEvidence
    -> TRACE record and consumer decision
    -> authorized ActionInstance
    -> asset motion and outcome events
    -> revision and local repair
    -> WebSocket snapshot back to the browser
```

## API

```text
GET  /api/state
GET  /api/events
GET  /api/records
POST /api/control/start
POST /api/control/pause
POST /api/control/step
POST /api/control/reset
POST /api/control/speed
POST /api/emergency-call
POST /api/events
POST /api/plan
POST /api/export
WS   /ws
```

Interactive OpenAPI documentation is available at:

```text
http://127.0.0.1:8000/docs
```

## Artifacts

Each run writes under:

```text
artifacts/dynamic/<run_id>/
├── events/simulation.jsonl
├── records/trace.jsonl
├── evidence/*.json
├── commitments/commitments.jsonl
└── run_manifest.json
```

`simulation.jsonl` and `trace.jsonl` are independently hash-chained.

## Validation

```bash
pytest
```

The dynamic tests cover:

- hidden truth does not appear in initial controller knowledge;
- S1 controls are versioned and applied;
- S2 water can close a previously open route;
- S3 repeated planning does not double-assign one group;
- S4 shocks are event-sourced;
- S5 operator reconnaissance requests become actual survey actions;
- event replay reconstructs byte-equivalent state;
- FastAPI exposes state and accepts control events.
- pickup is distinct from safe delivery;
- return-to-safety is separately TRACE-gated and uses only waterway segments;
- repeated emergency calls update or merge one incident using explicit count semantics;
- the JavaScript asset animation contract remains present and syntactically valid.

## Known limitations

- the predictor is a deterministic/stochastic surrogate, not V-JEPA;
- the local 100-by-80 map is not yet geospatial;
- water dynamics are deliberately simple and inspectable;
- one FastAPI process owns one default run;
- no authentication or multi-user conflict resolution;
- Incident Commander authority is a UI Boolean, not an identity-backed workflow;
- clearance validity is represented, but the next release will make proactive expiry a first-class
  action-dispatch check;
- charts are browser-native and intentionally dependency-free.

## Next implementation increment

D1 will deepen S1 rather than immediately adding model scale:

1. persist synchronized observation/action/outcome windows;
2. replace hand-shaped support/OOD formulas with estimators fit on held-out trajectories;
3. add calibration and reliability exports;
4. add the audit-condition selector (raw, confidence, explanation, single-pass TRACE, staged TRACE);
5. add batch paired-seed experiment execution.

The first V-JEPA integration follows the stable model-service interface after the dynamic and
measurement paths are reliable.
