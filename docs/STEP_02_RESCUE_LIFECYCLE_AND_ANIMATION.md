# D0.2 Step 2: Complete Rescue Lifecycle, Alert Counts, and Asset Animation

## Why this step exists

Step 1 made boat motion physically valid: an authorized boat path is a sequence of waterway edges rather than a straight line. Step 2 corrects three remaining operational ambiguities:

1. reaching the incident is **pickup**, not rescue completion;
2. a repeated or new alert must update the visible incident count unambiguously; and
3. the map should show recognizable, moving drones and boats rather than generic circles.

The full source remains in the repository. This guide explains the contracts and points to the exact files.

## Operational decision: where does the boat go after pickup?

The default lifecycle is:

```text
TRACE-gated outbound dispatch
    -> arrive at incident
    -> refresh route observation
    -> board people
    -> PEOPLE_PICKED_UP (not yet rescued)
    -> new TRACE-gated evacuation decision
    -> return on waterway graph to Safe Transfer Dock
    -> unload and hand off people
    -> PEOPLE_DELIVERED
    -> boat enters STANDBY at the safe dock
```

In the current Riverside scenario, the Safe Transfer Dock is co-located with the Rescue Base. Therefore, the boat returns to the starting area, unloads, and parks there ready for another assignment. The safe location remains a distinct mission object so a later scenario can place it elsewhere.

A group is counted as rescued only after `PEOPLE_DELIVERED`, never at `PEOPLE_PICKED_UP`.

## Source files

| Responsibility | Exact source |
|---|---|
| Lifecycle state fields | `src/trace_jepa/workbench/models.py` |
| Pickup, onboard, delivered, standby reducers | `src/trace_jepa/workbench/reducer.py` |
| Separate evacuation candidates and TRACE records | `src/trace_jepa/workbench/controller.py` |
| Boarding/unloading schedules and action completion | `src/trace_jepa/workbench/engine.py` |
| Graph-valid return route | `src/trace_jepa/workbench/navigation.py` |
| Safe dock and no pre-seeded UI incident | `configs/scenarios/riverside_flood_dynamic_v2.yaml` |
| Emergency-call count semantics | `src/trace_jepa/workbench/api.py` |
| Boat/drone SVG animation | `src/trace_jepa/workbench/static/app.js` |
| Animation and state styling | `src/trace_jepa/workbench/static/styles.css` |
| Regression and lifecycle tests | `tests/test_rescue_lifecycle_and_alert_merge.py` |

## Lifecycle contracts

### Group counts

Every group maintains three disjoint counts:

```text
people_waiting + people_onboard + people_delivered = people
```

The invariant is enforced by the `GroupState` model validator.

### Boat manifest

A rescue boat carries:

```text
passenger_count
passenger_group_ids
safe_location_id
mission_phase
```

The incident marker remains at the call location. People in transit are shown on the boat through its passenger badge. This prevents the incident itself from appearing to move across the map.

### Pickup is not delivery

`PEOPLE_PICKED_UP`:

- decreases `people_waiting`;
- increases `people_onboard`;
- adds the group to the boat manifest;
- changes the boat to `awaiting_clearance`;
- requests another planning cycle;
- does **not** increment `rescued_people`.

`PEOPLE_DELIVERED`:

- moves onboard counts to delivered counts;
- increments `rescued_people`;
- clears the boat manifest;
- places the boat in standby at the Safe Transfer Dock.

## Why TRACE runs again after pickup

The outbound route record licenses only travel from base to the incident. It does not silently authorize the return leg.

When passengers are onboard, the controller creates a new action:

```text
evacuate_to_safety(
  boat,
  onboard_groups,
  candidate_water_route,
  safe_transfer_dock
)
```

Each return route receives:

- a new prediction;
- a new predictive claim;
- a new `WorldModelEvidence` object;
- a new TRACE record;
- a separate authority and consumer decision.

Successful outbound traversal also creates a fresh route observation. This prevents the return decision from relying on a stale report when the boat has just directly observed the route during traversal.

## Emergency-call count semantics

The call form now requires the operator to choose one of two meanings:

### Current total still waiting

```text
The caller reports that 7 people are currently waiting.
```

A repeated call at the same active incident updates the marker to 7 rather than adding another marker or doubling the count.

### Additional people at this incident

```text
Three additional people have joined the same incident.
```

The system emits `INCIDENT_MERGED` and adds 3 to the existing waiting count.

The API response and visible status panel report:

```text
resolution
incident ID
waiting
onboard
delivered
alert count
```

The default dynamic UI scenario starts with no pre-seeded four-person incident, so the first submitted alert determines the first visible circle.

## Realistic browser animation

The map remains a lightweight SVG research interface, but assets are now recognizable and animated:

### Drone

- quadrotor body and camera;
- four independently rotating rotor glyphs;
- small hover motion;
- heading rotation;
- smooth translation between snapshots.

### Boat

- hull, cabin, windows, antenna, and wake;
- heading rotation;
- bobbing motion;
- moving wake animation;
- onboard passenger badge;
- smooth translation along the executable waterway segments.

The animation is presentation only. The simulator state and graph path remain authoritative.

## Run and verify

```bash
source "$HOME/miniforge3/etc/profile.d/conda.sh"
conda activate trace-jepa
python -m pip install -e ".[ui,dev]"
pytest tests/test_rescue_lifecycle_and_alert_merge.py -q
pytest -q
node --check src/trace_jepa/workbench/static/app.js
trace-jepa-ui --host 127.0.0.1 --port 8000
open http://127.0.0.1:8000
```

Or run the packaged verification command:

```bash
./scripts/verify_step02.sh
```

Expected test result for this release:

```text
33 passed
```

## Manual walkthrough

1. Submit `5` people with **Current total still waiting**.
2. Confirm the marker and status panel display `5`.
3. Submit `7` at the same location with **Current total still waiting**.
4. Confirm one marker now displays `7` and the alert badge shows `2`.
5. Submit `3` with **Additional people at this incident**.
6. Confirm the one marker now displays `10` and the alert badge shows `3`.
7. Start the simulation.
8. Observe the drone and boat animations.
9. At pickup, confirm the incident changes to “pickup complete” and the boat shows its passenger badge.
10. Confirm TRACE writes a separate evacuation decision.
11. Observe the boat return through waterway edges to the Safe Transfer Dock.
12. Confirm delivered count increases only after unloading and the boat enters standby.

## Exit conditions

```text
[ ] Pickup does not increment rescued_people.
[ ] Evacuation to safety has a separate TRACE record.
[ ] The return route contains only waterway segments.
[ ] The boat unloads at the declared safe location.
[ ] The boat enters standby after handoff.
[ ] Current-count alerts replace the visible waiting count.
[ ] Additional-person alerts add to the incident count.
[ ] Same-location alerts do not stack stale markers.
[ ] Drone rotors and boat movement animate in the browser.
[ ] The full Python suite and JavaScript syntax check pass.
```

## Still outside Step 2

- continuous background drone coverage and interrupt/resume;
- a distinct safe site connected by a separate waterway branch;
- dependency-indexed `TraceOperationalBinding`;
- hydrology forecast ensembles and proactive clearance expiry;
- complete helicopter and ground-team pickup/transport/handoff lifecycles;
- the learned V-JEPA world model.
