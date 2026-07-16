# Flood-SAR Implementation in Eight Verified Steps

This document describes the implementation that is actually present in the repository. It does not treat the deterministic teaching fixtures as experimental results.

## Scope and terminology

The implementation has one central `MissionController`, one simulated `FloodEnvironment`, a survey drone, a rescue boat, and a teaching stand-in for a human `IncidentCommander`. The planner, predictor, TRACE gate, and dispatcher are modules inside the Mission Controller. Simulation ground truth is never passed to the controller's planning or gating functions.

The **eight operational steps** below are distinct from the **eight TRACE writer stages** in the specification paper. A crosswalk appears after Step 8.

## Run the complete episode

```bash
source "$HOME/miniforge3/etc/profile.d/conda.sh"
conda activate trace-jepa
cd "$HOME/Projects/trace_jepa_flood_sar_starter"
python -m pip install -e ".[dev]"

trace-jepa-call \
  --call-file examples/calls/riverside_call.txt \
  --output artifacts/runs/call_001
```

The command writes a detailed fourteen-event timeline. The eight steps below group those events by architectural responsibility.

---

## Step 1 - Accept and ground the emergency call

**Input:** raw emergency-call text.

**Code:**

- `src/trace_jepa/intake.py`
  - `resolve_location(...)`
  - `parse_people_count(...)`
  - `EmergencyCallIntake.parse(...)`
- `src/trace_jepa/emergency_cli.py`
  - `_read_call_text(...)`
  - `run_from_emergency_call(...)`

**Behavior:**

1. Preserve the complete call text.
2. Match a location through the scenario's closed alias registry.
3. extract the number of people.
4. use the scenario deadline unless an explicit override is supplied.
5. reject an ambiguous call instead of inventing coordinates or a people count.

**Output:** an immutable `EmergencyCall` object and `emergency_call.json`.

**Exit test:** the call resolves to `riverside_apartments`, `people_count=4`, and `deadline_s=1200`.

---

## Step 2 - Register the incident and build Mission Controller knowledge

**Input:** the grounded `EmergencyCall`.

**Code:**

- `src/trace_jepa/scenario/flood_env.py`
  - `register_emergency_call(...)`
  - `observe(...)`
  - `simulation_ground_truth(...)`
- `src/trace_jepa/fusion/state.py`
- `src/trace_jepa/scenario/visualize.py`

**Behavior:**

1. Update mission destination, people count, and deadline.
2. Expose only information legitimately available to Mission Control.
3. Keep the North Channel's hidden blockage outside the controller state until a sensing action reveals it.
4. Retain a separate simulation-ground-truth view for tests and after-the-fact evaluation.

**Output:** controller-visible observation, fused state hash, and two teaching visualizations.

**Exit test:** controller knowledge says `north_channel.report=unknown`; simulation truth says `north_channel=blocked`.

---

## Step 3 - Generate grounded candidate actions

**Input:** Mission Controller observation.

**Code:**

- `src/trace_jepa/planning/planner.py`
  - `FloodPlanner.propose(...)`
  - `FloodPlanner.choose(...)`
- `src/trace_jepa/contracts/models.py`
  - `ActionInstance`
  - `PlanCandidate`
- `configs/actions/flood_actions_v1.yaml`

**Behavior:** propose structurally possible actions without predicting or authorizing them.

Initial candidates:

1. `dispatch_rescue_boat` via `north_channel`.
2. `verify_route` for `north_channel` with `survey_drone_1`.
3. `dispatch_rescue_boat` via `south_detour`.

Each action names actor, origin, destination, route, people count, and deadline.

**Output:** a list of `PlanCandidate` objects.

**Exit test:** the three initial candidates are present and all actions are fully grounded.

---

## Step 4 - Predict consequences and formulate typed claims

**Input:** one candidate plan plus the controller-visible observation.

**Code:**

- `src/trace_jepa/predictor/toy.py`
  - `ToyActionPrefixPredictor.predict(...)`
- `src/trace_jepa/claims/probes.py`
  - `FloodClaimProbe.build_claim(...)`
- `src/trace_jepa/controller.py`
  - `MissionController._make_evidence(...)`

**Behavior:**

1. Produce a deterministic `PlanPrediction` teaching fixture.
2. Convert the prediction into a grounded **predictive** claim.
3. create `WorldModelEvidence` containing plan success, model support, OOD score, uncertainty, horizon, assumptions, hashes, and versions.

**Important limitation:** the predictor is hardcoded and deterministic. It is not V-JEPA and its numbers are not empirical results.

**Exit test:** the northern plan has `success_probability=0.92`, `model_support=0.28`, and `OOD=0.82`, with those quantities stored separately.

---

## Step 5 - Write TRACE records and apply the gate

**Input:** typed claim, evidence object, action class, reversibility, and authority state.

**Code:**

- `src/trace_jepa/runtime/policy.py`
  - `PolicyEngine.evaluate(...)`
- `src/trace_jepa/runtime/runtime.py`
  - `TraceRuntime.assess(...)`
  - `TraceRuntime.consume(...)`
- `src/trace_jepa/runtime/storage.py`
- `configs/policies/trace_v1.yaml`

**Behavior:**

1. Store evidence in the evidence ledger.
2. apply hard checks for support, OOD, uncertainty, horizon, freshness, contradiction, and authority.
3. construct and append a `TraceRecord`.
4. append the Mission Controller's consumer decision as a new record version.

**Initial decisions:**

- North dispatch: `DEFER` / `HOLD`.
- Drone verification: `ACCEPT` / `CLEAR`.
- South dispatch: `ACCEPT` / `CLEAR`.

**Exit test:** the high `0.92` plan score cannot override the failed support and OOD gates.

---

## Step 6 - Select, commit, and execute the evidence-seeking action

**Input:** candidate plans plus TRACE consumer decisions.

**Code:**

- `src/trace_jepa/planning/planner.py`
  - `FloodPlanner.choose(...)`
- `src/trace_jepa/runtime/runtime.py`
  - `TraceRuntime.commit(...)`
- `src/trace_jepa/controller.py`
  - `MissionController.run_episode(...)`, initial selection and dispatch
- `src/trace_jepa/scenario/flood_env.py`
  - `FloodEnvironment.execute(...)` for `verify_route`

**Behavior:** select the highest-utility candidate whose decision is `clear` or `qualify`. The verification action outranks the supported but slower south dispatch and is committed with its authorizing record ID/version.

The environment executes the drone action, reduces battery, and returns the observed route status.

**Output:** commitment object plus observation that the North Channel is blocked.

**Exit test:** the drone observation is produced only after an authorized `verify_route` action.

---

## Step 7 - Revise append-only and locally replan

**Input:** the realized drone observation and the prior northern-route record.

**Code:**

- `src/trace_jepa/controller.py`
  - `MissionController.run_episode(...)`, contradiction and replanning block
- `src/trace_jepa/runtime/runtime.py`
  - `TraceRuntime.revise_with_outcome(...)`
- `src/trace_jepa/planning/planner.py`
  - `FloodPlanner.propose(...)` after the route report becomes `blocked`

**Behavior:**

1. Attach the realized observation as a new evidence object.
2. create a new record version that supersedes the old northern-route record.
3. set the revised status to `REJECT` and add `realized_contradiction`.
4. observe the world again and regenerate candidates.
5. exclude the blocked route while preserving the completed drone action and unrelated state.

**Important limitation:** locality is currently realized by route-specific candidate filtering. The demo does not yet contain a general HTN dependency graph or arbitrary branch invalidation algorithm.

**Exit test:** the old record remains readable, the revision points to it, and the replanned candidate set contains the South Detour but not the blocked northern dispatch.

---

## Step 8 - Clear the final dispatch, execute rescue, and persist the audit trail

**Input:** replanned South Detour candidate, its TRACE record, and incident-command authority.

**Code:**

- `src/trace_jepa/controller.py`
  - `IncidentCommander.authorizes(...)`
  - final selection, commitment, dispatch, and summary
- `src/trace_jepa/runtime/runtime.py`
  - `TraceRuntime.commit(...)`
- `src/trace_jepa/scenario/flood_env.py`
  - `FloodEnvironment.execute(...)` for `dispatch_rescue_boat`
- `src/trace_jepa/reporting.py`
- `src/trace_jepa/emergency_cli.py`

**Behavior:**

1. Reassess and clear the South Detour.
2. record the incident-command authorization boundary.
3. create a final commitment that cites the exact TRACE record version.
4. execute the simulated boat rescue.
5. write timeline, summary, evidence, record history, commitments, and figures.

**Important limitation:** `IncidentCommander.authorizes(...)` is a deterministic teaching stub, not a human approval user interface.

**Exit test:** four people are reached, `record_chain_valid=True`, and every durable action has an authorizing record reference.

---

## Crosswalk to the eight TRACE writer stages

The general TRACE specification names eight writer stages: detect, intake, type, question, test, elicit, settle, and complete. This flood implementation is a **domain-structured writer**, not yet the full general-purpose natural-language writer.

| TRACE writer stage | Flood implementation |
|---|---|
| 0 Detect | The planner emits an explicit action-licensing claim candidate; no open-ended argument detector is used. |
| 1 Intake | `FloodClaimProbe` and `_make_evidence` fill claim, grounding, provenance, assumptions, and evidence. |
| 2 Type | Claims are explicitly typed `ClaimLayer.PREDICTIVE`. |
| 3 Question | Policy requirements stand in for the domain's critical-question battery: support, OOD, uncertainty, horizon, freshness, contradiction, authority. |
| 4 Test | `PolicyEngine.evaluate` runs those deterministic checks. |
| 5 Elicit | A failed northern claim emits a repair request: obtain a current route observation through a bounded drone action. No debate module is implemented. |
| 6 Settle | The deterministic policy maps failures to `HOLD`, `CLEAR`, `QUALIFY`, `BLOCK`, or `ESCALATE`. No attack-graph semantics are implemented in this demo. |
| 7 Complete | `TraceRuntime.assess` writes verdict, failed gates, missing items, repair, provenance, and the consumer action to append-only storage. |

The deck and code must preserve this boundary. It is incorrect to claim that the full general-purpose eight-stage writer has already been implemented.

## Detailed event log versus eight architectural steps

The CLI prints fourteen human-readable events. The mapping is:

| Eight-step group | Detailed events |
|---|---|
| 1 Call intake | 01 |
| 2 Mission state | 02 |
| 3 Candidate planning | internal, summarized by 03-05 |
| 4 Prediction and claims | internal, summarized by 03-05 |
| 5 TRACE gate | 03-05 |
| 6 Verification action | 06-08 |
| 7 Revision and repair | 09-11 |
| 8 Final rescue | 12-14 |

## Definition of done

The teaching implementation is complete when a reviewer can reconstruct from stored files:

1. the raw call and its normalized mission location;
2. the controller-visible state at each decision;
3. each candidate action and predictive evidence object;
4. each TRACE verdict, failed gate, missing item, and repair;
5. each consumer decision and commitment;
6. the realized observation or outcome;
7. each append-only revision;
8. the final rescue action and its authorizing record version.
