# Student Tutorial: Build TRACE-JEPA for Flood Search-and-Rescue

This tutorial starts at ground zero and ends with a small closed-loop system. Work through it in order. Each phase has a purpose, an input, an output, and an exit condition.

> **Companion tutorial deck.** For live teaching, use `docs/eight_step_deck/TRACE_JEPA_Flood_SAR_8_Steps.pptx` or its PDF export. The deck follows the actual call-to-rescue implementation in eight verified operational steps. Short source excerpts appear directly in the slides; complete exact copies are in `docs/eight_step_deck/side_files/`, grouped as `step01_...` through `step08_...`. See `docs/EIGHT_STEP_IMPLEMENTATION.md` and `docs/eight_step_deck/side_files/CODE_MAP.md`.


---

## 0. Mission briefing before code

Read [`MISSION_BRIEF.md`](MISSION_BRIEF.md). You should be able to name every operational entity before opening Python. Keep [`TRACE_RECORD_WALKTHROUGH.md`](TRACE_RECORD_WALKTHROUGH.md) beside you as the artifact-level map of the episode.

### The world

The **Flood Environment** is the simulated world. It owns hidden route status and produces observations and consequences.

### The physical agents

- `survey_drone_1` observes a requested route and reports what it sees.
- `rescue_boat_1` executes an authorized route and transports residents.

Neither physical agent plans the mission or runs TRACE in this first implementation.

### The central software

The **Mission Controller** is one program running at the command post. It contains:

```text
Mission State       what has been reported
Planner             what actions are structurally possible
World Model         what may happen under each candidate
TRACE Gate          whether recorded evidence may authorize action
Action Dispatcher   which cleared command is sent
```

### Human authority

The **Incident Commander** approves consequential dispatch classes. The first demo uses a deterministic authority fixture. That fixture is not a substitute for a real approval interface.

### Offline evaluation

There is no operational evaluator agent. An offline research procedure may inspect logs and simulation ground truth after the episode. It sends no commands during the mission.

### The test case

Four residents are waiting at Riverside Apartments. The North Channel is fast but unverified. The South Detour is slower but reported open. Hidden simulation truth says the North Channel is blocked.

The intended sequence is:

```text
north dispatch proposed
  -> high predicted success but weak support
  -> TRACE HOLD
  -> drone verification cleared
  -> obstruction observed
  -> append-only revision
  -> south dispatch cleared
  -> rescue completed
```

**Do not proceed until you can explain that the drone only reports observations, the Flood Environment owns hidden truth, and offline scoring occurs only after the episode.**

---

## 1. Ground-zero environment setup

### 1.1 Check the machine

```bash
git --version
python --version
conda --version
uname -m
```

For Apple Silicon, prefer a native `osx-arm64` Conda installation. Check:

```bash
conda info | grep platform
```

Expected:

```text
platform : osx-arm64
```

The course environment uses Python 3.12.

### 1.2 Create and activate the environment

```bash
conda create -n trace-jepa python=3.12 pip -y
conda activate trace-jepa
python --version
which python
```

Expected:

```text
Python 3.12.x
.../envs/trace-jepa/bin/python
```

On a Mac where you do not want to modify shell initialization, activate native Miniforge explicitly:

```bash
source "$HOME/miniforge3/etc/profile.d/conda.sh"
conda activate trace-jepa
```

### 1.3 Install the starter project

From the project root:

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
trace-jepa-verify
pytest
```

Core mode does not require PyTorch or a JEPA checkpoint.

**Exit condition:** the verifier passes and the core tests pass, with at most the optional PyTorch test skipped.

---

## 2. See the system before implementing it

Render three vector views from the same scenario file:

```bash
trace-jepa-visualize \
  --scenario configs/scenarios/riverside_flood_v1.yaml \
  --output artifacts/runs/scenario_brief
```

Open them on macOS:

```bash
open artifacts/runs/scenario_brief/operational_cast.svg
open artifacts/runs/scenario_brief/mission_controller_knowledge.svg
open artifacts/runs/scenario_brief/simulation_ground_truth.svg
```

The files are SVG vectors and can be opened in a browser, Inkscape, Illustrator, or included in teaching slides.

### What to inspect

1. `operational_cast.svg` shows the Mission Controller as the central program and separates the Flood Environment, physical agents, and human authority.
2. `mission_controller_knowledge.svg` shows the North Channel as **unverified**.
3. `simulation_ground_truth.svg` shows the hidden debris obstruction.

The second view is not an input to the Mission Controller.

**Exit condition:** you can explain why the two map views differ and identify who is allowed to see each one.

---

## 3. Inspect the scenario and action schema

Open:

```bash
cat configs/scenarios/riverside_flood_v1.yaml
cat configs/actions/flood_actions_v1.yaml
```

The scenario defines:

- the map and route geometry;
- the hidden route status;
- the initial report available to Mission Control;
- the drone and boat;
- the pickup location;
- the number of residents;
- the deadline.

The action schema defines the allowable action types. The implementation uses grounded `ActionInstance` objects rather than strings such as `dispatch_boat_north`.

A dispatch action has this shape:

```text
action_type: dispatch_rescue_boat
actor_id: rescue_boat_1
origin: rescue_base
destination: riverside_apartments
route_id: south_detour
parameters:
  people_count: 4
  deadline_s: 1200
```

A verification action has this shape:

```text
action_type: verify_route
actor_id: survey_drone_1
origin: drone_pad
destination: north_channel
route_id: north_channel
parameters:
  purpose: resolve_route_access
```

**Exit condition:** every proposed action has an actor, destination or sensing target, route when applicable, and mission parameters.

---

## 4. Freeze the durable contracts

Start with:

```text
src/trace_jepa/contracts/models.py
```

The durable objects are:

| Object | Meaning |
|---|---|
| `ActionInstance` | the grounded command being considered |
| `WorldModelEvidence` | what a named model version predicted from a named state and action |
| `Claim` | the grounded proposition extracted from that prediction |
| `TraceRecord` | evidence references, failed gates, missing items, repair, verdict, and provenance |
| `ConsumerAction` | what the Mission Controller does with that record |
| `Commitment` | the durable action actually authorized |
| `RealizedOutcome` | what the Flood Environment later revealed |

Run:

```bash
python scripts/print_contracts.py
pytest tests/test_repository.py tests/test_closure.py
```

First implementation rules:

1. committed objects are immutable;
2. revisions create new versions;
3. every durable dispatch cites an authorizing record version;
4. a failed hard gate cannot be averaged away by high predicted utility;
5. simulation ground truth never appears in Mission Controller knowledge before observation.

**Exit condition:** evidence and records serialize, reload, and hash-verify without losing fields.

---

## 5. Implement the TRACE runtime

Read the runtime in this order:

```text
src/trace_jepa/runtime/storage.py
src/trace_jepa/runtime/policy.py
src/trace_jepa/runtime/runtime.py
```

The runtime provides:

1. append-only TRACE repository;
2. evidence ledger;
3. versioned policy loader;
4. deterministic hard-gate evaluator;
5. record write transaction;
6. consumer decision transaction;
7. commitment log;
8. revision and hash-chain verification.

The public conceptual boundary is:

```text
build(...)   -> completed or pending TraceRecord
resume(...)  -> completed or pending TraceRecord
write(...)   -> immutable record identifier and version
consume(...) -> recorded consumer decision
```

### Tamper exercise

Run the repository test, then intentionally alter one committed JSON line in a disposable run and confirm that chain verification fails.

**Exit condition:** closure, deterministic gates, version coherence, and hash-chain verification have executable tests.

---

## 6. Understand the first predictor before trusting it

Open:

```text
src/trace_jepa/predictor/toy.py
```

This predictor is a deterministic test fixture. It is keyed to a grounded action and the Mission Controller's reported route state.

For an unverified dispatch through the North Channel it emits:

```text
predicted plan success probability: 0.92
model support:                      0.28
out-of-distribution score:          0.82
uncertainty:                        0.08
```

The semantic probe currently copies the plan-success estimate into the combined claim confidence so students can see the full path. Later labs replace this shortcut with predicate-specific calibration.

Hardcoded fixtures are normal for unit tests and teaching examples. They are not acceptable as experimental evidence. Their purpose is to test whether the surrounding system responds correctly to a known input.

**Exit condition:** you can distinguish plan utility, predicted plan success, claim confidence, model support, OOD score, and TRACE decision.

---

## 7. Accept an emergency call and watch the actions

The first operational input is a phone report containing a location and number of people. Use the supplied call file:

```text
examples/calls/riverside_call.txt
```

Its contents are:

```text
Emergency. Four residents are stranded at Riverside Apartments.
Flood water is rising and the road is inaccessible.
```

Run the complete call-to-rescue episode:

```bash
trace-jepa-call \
  --call-file examples/calls/riverside_call.txt \
  --output artifacts/runs/call_001
```

Or provide the call inline:

```bash
trace-jepa-call \
  --call "Emergency. Four residents are stranded at Riverside Apartments." \
  --output artifacts/runs/call_002
```

The intake module performs deterministic grounding:

```text
raw call -> Riverside Apartments -> riverside_apartments
         -> four residents       -> people_count = 4
         -> scenario deadline    -> deadline_s = 1200
```

If the location or people count cannot be parsed, the program stops and asks for an explicit override:

```bash
trace-jepa-call \
  --call "People are trapped and need a boat." \
  --location "Riverside Apartments" \
  --people 4 \
  --output artifacts/runs/call_003
```

The terminal then prints the actions as they happen:

```text
CALL RECEIVED
MISSION STATE
PLAN ASSESSED: north dispatch -> HOLD
PLAN ASSESSED: drone verification -> CLEAR
ACTION SELECTED: survey drone verifies North Channel
OBSERVATION RECEIVED: North Channel blocked
TRACE REVISED
REPLANNING
FINAL ACTION SELECTED: boat uses South Detour
RESCUE OUTCOME: success
```

Inspect the generated artifacts:

```bash
cat artifacts/runs/call_001/timeline.txt
open artifacts/runs/call_001/figures/mission_controller_knowledge.svg
open artifacts/runs/call_001/figures/action_timeline.svg
cat artifacts/runs/call_001/summary.json
```

The main code path is:

```text
src/trace_jepa/emergency_cli.py     terminal entry point
src/trace_jepa/intake.py            location and people grounding
src/trace_jepa/scenario/flood_env.py registers the call as the mission
src/trace_jepa/controller.py        emits the live action timeline
src/trace_jepa/reporting.py         writes timeline.txt and action_timeline.svg
```

**Exit condition:** the first line of the timeline is the grounded emergency call, and the last line is a successful rescue outcome.

---

## 8. Run the complete mock episode

Run:

```bash
trace-jepa-demo --output artifacts/runs/mock_closed_loop
```

Inspect:

```bash
cat artifacts/runs/mock_closed_loop/summary.json
```

The summary should explicitly name the operational cast and show a north-route assessment resembling:

```text
predicted_plan_success_probability: 0.92
claim_confidence:                    0.92
model_support:                       0.28
out_of_distribution_score:          0.82
decision:                            hold
```

Expected sequence:

1. Planner proposes `north-direct`, `verify-north`, and `south-detour`.
2. TRACE holds the unsupported north dispatch.
3. The Mission Controller commits the drone verification action.
4. The Flood Environment reveals a blocked route to the drone.
5. A revision rejects the earlier north-route claim without deleting it.
6. Planner removes only the route-dependent north branch.
7. TRACE clears the south dispatch.
8. The Mission Controller dispatches `rescue_boat_1` to `riverside_apartments` via `south_detour`.

Run the focused tests:

```bash
pytest tests/test_policy.py tests/test_end_to_end.py
```

**Exit condition:** the final commitment cites the exact TRACE version that cleared it, and the repository chain verifies.

---

## 9. Who runs what in the code

The central orchestration object is:

```text
src/trace_jepa/controller.py::MissionController
```

Its modules are:

```text
FloodPlanner                 proposes actions
ToyActionPrefixPredictor     predicts candidate consequences
FloodClaimProbe              emits grounded predictive claims
TraceRuntime                 writes records and applies policy
IncidentCommander fixture    supplies external authorization status
FloodEnvironment             executes authorized actions
```

`MissionController` calls TRACE. The drone does not run TRACE. The Flood Environment does not run TRACE. Offline evaluation does not run during the mission.

---

## 10. Download the V-JEPA 2.1 encoder

Do this only after the mock loop passes.

### 9.1 Role of the downloaded model

The course uses V-JEPA 2.1 as a frozen visual representation backbone. Students still train a separate flood-domain action-conditioned predictor.

### 9.2 Install optional dependencies

Install the correct PyTorch build for the machine first, then:

```bash
pip install -e ".[jepa]"
```

A CUDA machine is strongly preferred for repeated video inference. Core mode remains laptop-safe.

### 9.3 Download through the course wrapper

```bash
trace-jepa-download \
  --model vjepa2_1_vit_base_384
```

The wrapper:

1. constructs the official architecture from a pinned upstream revision;
2. downloads the official checkpoint under `models/external/vjepa2/`;
3. verifies the encoder state dictionary;
4. writes a manifest with source revision, URL, local path, size, SHA-256, Python, PyTorch, and timestamp.

### 9.4 Optional source checkout

```bash
mkdir -p third_party
git clone https://github.com/facebookresearch/vjepa2.git third_party/vjepa2
git -C third_party/vjepa2 checkout 204698b45b3712590f06245fbfba32d3be539812
pip install -e third_party/vjepa2
```

Keep third-party code and licenses outside `src/trace_jepa`.

### 9.5 macOS note

The course feature-cache path uses OpenCV rather than the upstream `decord` path. Linux or a tested GPU container is still the safer environment for upstream demonstrations and training.

**Exit condition:** a checksum-bearing model manifest exists and the encoder instantiates without changing course source.

---

## 11. Encode one ethically sourced video

Place a short controlled clip at:

```text
data/raw/demo/flood_clip.mp4
```

Record its source, license, consent or privacy basis, and intended use in `data/manifests/`.

Run:

```bash
python scripts/encode_video.py \
  --video data/raw/demo/flood_clip.mp4 \
  --output data/processed/demo/flood_clip_vjepa.npz
```

The cache stores:

- embedding;
- sampled frame indices;
- video hash;
- model entry point;
- model-manifest reference;
- feature shape.

**Exit condition:** the same clip and manifest reproduce the same input hash, frame indices, and feature shape.

---

## 12. Build synchronized trajectory windows

A predictor training example is not only video. It is:

```text
observation window
+ drone and boat telemetry
+ route and flood map state
+ communication state
+ mission state
+ grounded action prefix
+ realized future predicates
```

Use [`DATA_CONTRACT.md`](DATA_CONTRACT.md). Labels belong to the realized future and must not leak into the input state.

Start with:

```bash
python scripts/generate_synthetic_dataset.py \
  --episodes 1000 \
  --output data/processed/synthetic_flood_trajectories.npz
```

**Exit condition:** every label is computed from the future outcome, while the model input contains only information available at decision time.

---

## 13. Train a flood-domain action predictor

The first trainable model receives:

```text
cached visual or mock embedding
+ structured mission state
+ grounded candidate action
```

and predicts:

```text
route success probability
arrival time
hazard score
remaining resource margin
```

Train:

```bash
python scripts/train_action_predictor.py \
  --dataset data/processed/synthetic_flood_trajectories.npz \
  --output models/checkpoints/toy_action_predictor.pt \
  --epochs 100
```

The script fits normalization on training data only, uses a reproducible held-out split, restores the best checkpoint, and compares against a constant baseline.

**Exit condition:** the checkpoint beats the declared baseline and its manifest names the dataset hash, split seed, action schema, normalization, and training snapshot.

---

## 14. Build calibrated semantic probes

A latent vector is not yet an operational claim. Define explicit predicates such as:

```text
route_open(route_id, horizon)
arrival_before(actor_id, destination, deadline)
rescue_capacity_sufficient(actor_id, people_count)
resource_margin_positive(actor_id, horizon)
```

For each predicate:

1. define grounding and units;
2. train on the training split;
3. choose thresholds on a calibration split;
4. evaluate on untouched test scenarios;
5. version the probe and threshold together;
6. emit `WorldModelEvidence`, not free-form narration.

Every evidence object carries model versions, observation and action hashes, horizon, uncertainty, support, OOD measure, assumptions, and calibration version.

**Exit condition:** every operational forecast is a typed, grounded, versioned evidence object.

---

## 15. Apply the TRACE commitment gate

The initial policy is:

```text
configs/policies/trace_v1.yaml
```

The gate checks:

- observation freshness;
- model support;
- OOD score;
- calibrated horizon;
- uncertainty;
- contradiction;
- incident-command authority.

The central test remains:

```text
high predicted success
+ high claim confidence
+ action outside calibrated support
= HOLD, not COMMIT
```

A supported alternative or reversible verification action should remain available. TRACE localizes the hold rather than freezing the entire mission.

**Exit condition:** plan utility cannot override a failed hard gate.

---

## 16. Attach outcomes and repair locally

After an authorized action:

1. Flood Environment returns a `RealizedOutcome`;
2. Mission Controller writes it as new evidence;
3. TRACE creates a revision when a decisive contradiction occurs;
4. Planner identifies the commitments licensed by the failed claim;
5. only those branches are repaired;
6. unaffected observations and records remain valid.

Run:

```bash
pytest tests/test_end_to_end.py
```

The test proves that:

- the original prediction remains readable;
- the revision cites the original record;
- the invalidated branch is localized;
- the repaired dispatch cites a new authorizing record;
- the repository hash chain verifies.

**Exit condition:** the episode ends with no unrecorded durable transition.

---

## 17. Replace synthetic components gradually

Use this transfer order:

1. synthetic observations and telemetry;
2. real video with synthetic telemetry;
3. real video with recorded telemetry;
4. replayed drone or rescue-boat logs;
5. controlled field exercises with no autonomous dispatch authority;
6. independent flood-simulator disturbances;
7. broader weather, terrain, platform, and communication conditions.

At every transition:

- declare a new operating envelope;
- create a new data snapshot and manifest;
- recalibrate support and uncertainty;
- rerun TRACE hard-gate tests;
- preserve old versions for replay;
- obtain privacy, data-license, and incident-command review.

Never reuse synthetic thresholds silently in a real setting.

---

## 18. Six-lab sequence

| Lab | Student deliverable | Main concept | Exit test |
|---|---|---|---|
| 1 | mission briefing, vector scenario views, typed contracts, append-only repository | entity clarity and operational closure | student distinguishes controller knowledge from hidden truth; tamper detection passes |
| 2 | mock flood-SAR closed loop | commitment gating | unsupported high-confidence north dispatch is held |
| 3 | V-JEPA feature cache and manifest | frozen representation | reproducible video hash and feature shape |
| 4 | action-prefix predictor checkpoint | learned dynamics | beats constant baseline on held-out data |
| 5 | calibrated semantic probes | latent-to-claim bridge | every claim has grounding, support, uncertainty, and version |
| 6 | surprise, revision, and local repair | accountable closed loop | original record preserved; dependent branch repaired |

A team should not advance until the preceding artifact can be replayed from named versions.

---

## 19. Common mistakes

### “The drone knows the whole world and scores the run.”

No. The drone is a sensor-bearing field agent. It observes only the requested region and reports that observation. Hidden truth belongs to the Flood Environment; offline scoring reads truth and logs only after the episode.

### “The Mission Controller should know what the simulator knows.”

No. The controller receives only declared observations and reports. Hidden state is used for outcomes and labels, not as a planning premise.

### “We downloaded V-JEPA, so we have a simulator.”

No. You have a visual representation backbone. You still need synchronized rescue data, grounded actions, an action-conditioned predictor, probes, calibration, and an external outcome source.

### “The plan has the highest predicted utility, so commit it.”

Not when a hard gate fails. Utility ranks admissible plans; it does not make unsupported plans admissible.

### “Confidence is 0.92, so support must be high.”

No. Confidence, model support, OOD, and uncertainty are different quantities. The demo is built specifically to expose this difference.

### “The model predicted the effect, so the claim is causal.”

Action-conditioned prediction is model-conditional. Causal interpretation needs additional assumptions and evidence.

### “We fixed the old JSON record.”

That destroys history. Add a linked revision.

---

## 20. Definition of done

A complete implementation can answer from stored artifacts alone:

1. What did the Mission Controller know at the decision time?
2. What hidden truth was unavailable to it?
3. Which physical agent was asked to do what, where, and for whom?
4. Which model, data snapshot, and action schema produced the forecast?
5. What was predicted, at what horizon, with what confidence, uncertainty, support, and OOD score?
6. Which claim licensed or failed to license the action?
7. Which policy and human authority cleared it?
8. What command was actually sent?
9. What happened in the Flood Environment?
10. Which record superseded the failed claim?
11. Which plan branches changed, and which remained valid?

That is the implementation target. Better encoders and predictors can be substituted without changing the accountability boundary.
