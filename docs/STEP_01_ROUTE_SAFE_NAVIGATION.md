# Step 1: Replace Straight-Line Boat Motion with a Waterway Graph

This is the first augmentation of the D0.1 code base. Do not begin with JEPA.
First make the simulator physically coherent and make every path auditable.

## Goal

After this step:

- a rescue boat moves only on waterway edges;
- a route switch uses graph connectors rather than a direct line;
- a blocked edge stops the boat at the last safe graph point;
- the UI draws the exact path the engine will execute;
- every S1-S5 change opens a visible reasoning cycle and identifies revised TRACE records.

## Files added or changed

```text
configs/scenarios/riverside_flood_v1.yaml
src/trace_jepa/workbench/models.py
src/trace_jepa/workbench/navigation.py          NEW
src/trace_jepa/workbench/scenario.py
src/trace_jepa/workbench/reducer.py
src/trace_jepa/workbench/engine.py
src/trace_jepa/workbench/controller.py
src/trace_jepa/runtime/runtime.py
src/trace_jepa/workbench/static/index.html
src/trace_jepa/workbench/static/styles.css
src/trace_jepa/workbench/static/app.js
tests/test_navigation_and_reasoning.py          NEW
tests/test_dynamic_workbench.py
```

## 1. Extend the scenario contract

Every route now declares a mobility mode and endpoints. Runtime state expands the route into
edge-level open/closed state.

```yaml
routes:
  north_channel:
    mode: water
    start_location: rescue_base
    end_location: riverside_apartments
    waypoints:
      - [12, 16]
      - [24, 33]
      - [42, 51]
      - [60, 64]
      - [78, 70]
      - [88, 66]
```

Open the full file:

```text
configs/scenarios/riverside_flood_v1.yaml
```

## 2. Add an executable path segment

`PathSegment` is the common object used by the planner, dispatcher, engine, UI, and log.

```python
class PathSegment(FrozenModel):
    route_id: str | None
    edge_index: int | None
    direction: Literal["forward", "reverse", "direct"]
    from_position: Position
    to_position: Position
    mode: Literal["water", "road", "air", "foot", "direct"]
```

For a boat, `mode` must be `water`; a direct segment is not accepted as a boat route.

Open the full file:

```text
src/trace_jepa/workbench/models.py
```

## 3. Build the graph router

The new module:

```text
src/trace_jepa/workbench/navigation.py
```

performs four jobs:

1. expands route polylines into directed graph edges;
2. removes edges that are blocked in the selected view;
3. uses Dijkstra search to connect the asset's current graph node to the selected route;
4. returns both display points and auditable `PathSegment` objects.

The public function is:

```python
plan_route_constrained_action(state, action, view="controller")
```

For boats it never returns a direct segment. Drones and helicopters may use direct aerial motion.

## 4. Execute the same path the planner returned

`DynamicRun._move_assets()` advances through `asset.path_segments`. Before entering a water
segment, it rechecks the corresponding truth edge. If that edge has become blocked, it emits:

```text
ACTION_INTERRUPTED
```

and stops at the current safe point. The engine does not interpolate toward the mission target.
It interpolates only toward `segment.to_position`.

Open:

```text
src/trace_jepa/workbench/engine.py
```

## 5. Render the executable path

The browser now draws remaining `path_segments`, not a guessed line from current position to
mission destination. What is displayed is what will be executed.

Open:

```text
src/trace_jepa/workbench/static/app.js
```

## 6. Make parameter changes explainable

A material S1-S5 event creates a `ReasoningCycle` with ordered stages:

```text
trigger
state
prediction
claim
trace
plan
commitment (when an action is selected)
```

The browser's right panel presents the latest cycle. TRACE revisions remain append-only and
appear in the lower TRACE tab.

## Install and test

From the D0.2 project root:

```bash
source "$HOME/miniforge3/etc/profile.d/conda.sh"
conda activate trace-jepa
python -m pip install -e ".[ui,dev]"
pytest
```

Expected result:

```text
26 passed
```

Run the focused tests:

```bash
pytest tests/test_navigation_and_reasoning.py -q
```

These tests prove:

- a boat at the North Channel hazard reverses on the network before taking South Detour;
- a boat stops at a newly blocked edge;
- an S1 parameter change creates an explicit reasoning cycle and TRACE revisions;
- a truth-only shock does not revise controller TRACE records until observed.

## Start the browser

```bash
trace-jepa-ui --host 127.0.0.1 --port 8000
open http://127.0.0.1:8000
```

## Manual verification exercise

1. Submit the Riverside emergency call.
2. Let the drone verify North Channel.
3. Observe the South Detour boat path as a chain of waterway segments.
4. Switch to Truth view to inspect the blocked North edge.
5. Apply an S1 parameter change.
6. Read the right panel from change trigger through TRACE and plan update.

## Exit criterion

This step is complete only if all of the following hold:

```text
No boat position leaves a permitted waterway edge.
No return or reroute uses a direct coordinate line.
A newly blocked edge interrupts before traversal.
The map path is the engine path.
A material S1-S5 change identifies the reasoning and TRACE update it caused.
Replay and both hash chains remain valid.
```
