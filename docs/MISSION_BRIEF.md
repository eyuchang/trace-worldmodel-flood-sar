# Mission Brief: Riverside Flood Search-and-Rescue

Read this before running code. The demonstration has one simulated world, two physical agents, one central software application, and one human authority role.

## One-sentence mission

Four residents are isolated at Riverside Apartments. A rescue boat at the Rescue Base must reach them within twenty minutes. The North Channel is shorter but unverified; the South Detour is slower but reported open. A survey drone can inspect the North Channel before the boat is dispatched.

## How the episode begins

The operational input is an emergency call, not a pre-filled plan:

```text
Emergency. Four residents are stranded at Riverside Apartments.
Flood water is rising and the road is inaccessible.
```

A deterministic intake module preserves the raw call and grounds three fields:

```text
normalized_location_id: riverside_apartments
people_count:           4
deadline_s:             1200
```

The first teaching scenario uses a closed location registry. A later version can replace the resolver with address validation and geocoding without changing the EmergencyCall or TRACE contracts.


## The operational cast

| Entity | What it is | What it does | What it does **not** do |
|---|---|---|---|
| **Flood Environment** | The simulated world | Owns roads, water, debris, hidden route status, and action consequences | It does not plan or authorize actions |
| **Survey Drone** | A physical agent, simulated first | Observes a requested route and reports the observation | It does not own hidden truth, plan the mission, run TRACE, or score the episode |
| **Rescue Boat** | A physical agent, simulated first | Executes an authorized route and rescues residents | It does not choose the macro-level route |
| **Mission Controller** | One central program at the command post | Maintains mission knowledge, proposes actions, predicts consequences, calls TRACE, and dispatches cleared actions | It does not own hidden ground truth |
| **Incident Commander** | Human authority role | Approves consequential dispatch classes | TRACE cannot synthesize this authority |
| **Offline Evaluation** | A research procedure run after an episode | Reads logs and simulation ground truth to score the run | It is not an operational actor and sends no commands |

Inside the **Mission Controller** are five software modules:

```text
Mission Controller
├── Mission State       what has been reported to the command post
├── Planner             proposes structurally possible actions
├── World Model         predicts consequences of each candidate
├── TRACE Gate          checks whether recorded evidence may authorize action
└── Action Dispatcher   sends only cleared commands
```

TRACE is therefore not a separate robot or decision-maker. It is a policy-gated record service called by the Mission Controller.

## What each party knows at the start

### Simulation ground truth

```text
North Channel: blocked by debris
South Detour: open
Residents: 4 at Riverside Apartments
```

### Mission Controller knowledge

```text
North Channel: unknown, not recently observed
South Detour: reported open
Survey drone: available, battery 82%
Rescue boat: at Rescue Base, capacity 6
Residents: 4 at Riverside Apartments
```

The North Channel obstruction is deliberately absent from the Mission Controller state. It becomes available only after the drone observes and reports it.

## The three candidate actions

### A. Dispatch through the North Channel

```text
action_type: dispatch_rescue_boat
actor_id: rescue_boat_1
origin: rescue_base
destination: riverside_apartments
route_id: north_channel
people_count: 4
deadline_s: 1200
```

The mock predictor assigns this plan a high success estimate, but the estimate lies outside declared model support:

```text
predicted plan success: 0.92
claim confidence:       0.92   # copied by the teaching probe only
model support:          0.28
OOD score:              0.82
```

TRACE should **hold** the irreversible dispatch.

### B. Verify the North Channel

```text
action_type: verify_route
actor_id: survey_drone_1
route_id: north_channel
purpose: resolve_route_access
```

This is a bounded information-gathering action. TRACE may clear or qualify it. The environment then reveals the obstruction to the drone, and the drone reports it to the Mission Controller.

### C. Dispatch through the South Detour

```text
action_type: dispatch_rescue_boat
actor_id: rescue_boat_1
origin: rescue_base
destination: riverside_apartments
route_id: south_detour
people_count: 4
deadline_s: 1200
```

After the northern route is confirmed blocked, the Planner repairs only the route-dependent branch and the supported southern dispatch can clear.

## The intended episode

```text
1. Flood Environment produces an incomplete observation.
2. Mission Controller stores that observation in Mission State.
3. Planner proposes north dispatch, drone verification, and south dispatch.
4. World Model predicts each candidate.
5. Semantic probe turns each prediction into a grounded claim.
6. TRACE holds the unsupported north dispatch.
7. TRACE permits the bounded drone verification action.
8. Drone observes debris and reports the blocked route.
9. A new TRACE revision preserves and supersedes the failed north-route claim.
10. Planner repairs only the dependent route branch.
11. Incident Commander authority plus a clear TRACE record authorize the south dispatch.
12. Rescue Boat executes the command; the environment supplies the realized outcome.
```

## What is hardcoded and why

The first predictor is a deterministic **test fixture**. Hardcoded cases are normal in unit tests and teaching demos because they make policy branches reproducible. They are not experimental results.

Hardcoded initially:

- a few predictor outputs;
- scenario ground truth;
- policy thresholds;
- authority available for declared action classes.

Replaced later:

- visual features by V-JEPA 2.1;
- prediction rules by a trained flood-domain action predictor;
- synthetic observations by recorded or simulated trajectories;
- the authority fixture by a real approval interface.

## What the demonstration proves

The core demo is successful when:

1. high numerical confidence does not override failed support gates;
2. a reversible evidence-gathering action remains possible;
3. hidden simulation truth never leaks into the Mission Controller state;
4. the wrong prediction remains in append-only history;
5. the new observation creates a linked revision;
6. only the dependent plan branch is repaired;
7. every dispatch cites its exact authorizing TRACE record version.

It does **not** yet prove that JEPA models floods accurately. It proves that the accountability architecture behaves correctly when a predictor is imperfect.
