# Entity Model: Who Does What?

The teaching system has **one simulated world, two simulated field assets, one central software application, and one human authority role**.

## Operational entities

### 1. Flood Environment

The `FloodEnvironment` is the simulated world. It contains the complete state of routes, water, debris, residents, and asset positions.

It performs two operations:

```text
observe(asset or mission controller) -> partial observation
apply(authorized action)             -> realized outcome
```

The environment is not a planner, model, evaluator, or decision-maker. It simply supplies observations and consequences according to its hidden state.

### 2. Fleet

The fleet contains two simulated field assets in the introductory episode:

- `survey_drone_1`: collects current route observations;
- `rescue_boat_1`: travels an authorized route and conducts the pickup.

The assets do not choose the mission-level plan in the first implementation. They execute structured commands sent by the mission controller.

### 3. Mission Controller

The `MissionController` is one central program running at the command post. It owns five software modules:

```text
MissionController
├── MissionState
├── CandidatePlanner
├── WorldModel
│   ├── VisualEncoder
│   └── ActionPredictor
├── TraceGate
└── ActionDispatcher
```

- **MissionState** stores only observations and legitimate inferences available at decision time.
- **CandidatePlanner** proposes structurally possible actions.
- **WorldModel** predicts model-conditional consequences of each candidate.
- **TraceGate** checks whether the recorded claims may authorize a specified action under a versioned policy.
- **ActionDispatcher** sends only cleared or qualified commands.

TRACE is not a separate robot or person. The mission controller calls the TRACE runtime before a durable commitment.

### 4. Incident Commander

The incident commander is the human authority for consequential rescue dispatch. TRACE may find the technical record admissible, but it cannot create legal, organizational, or moral authority.

The teaching demo uses an explicit simulated approval object so the authority boundary is visible in code. A real system would connect to a human interface and organizational policy.

## Offline research component

### Offline Experiment Scorer

After an episode, an offline script may compare actions, records, and outcomes with simulation ground truth to compute metrics.

The scorer is **not in the operational control loop**. It does not send commands and does not provide hidden truth to the mission controller.

Use these terms consistently:

| Avoid | Use instead |
|---|---|
| evaluator view | simulation ground truth |
| agent view | mission-controller knowledge |
| rescue system | mission controller, fleet, or full response system, whichever is intended |
| TRACE agent | TRACE gate or TRACE runtime |

## Who knows what?

| Entity | Initially knows North Channel is blocked? | Can authorize boat dispatch? |
|---|---:|---:|
| Flood Environment | yes | no |
| Survey Drone | no, until it observes the route | no |
| Rescue Boat | no | no |
| Mission Controller | no, until the drone report arrives | technically gates and dispatches |
| TRACE Gate | sees only the record and evidence supplied by mission control | returns a technical decision |
| Incident Commander | sees the presented operational record | yes, for governed actions |
| Offline Experiment Scorer | yes, after or outside the episode | no |

## Operational sequence

```text
Flood Environment
    -> partial observation
Mission Controller.MissionState
    -> candidate actions
Mission Controller.CandidatePlanner
    -> predicted consequences
Mission Controller.WorldModel
    -> typed claim and evidence
Mission Controller.TraceGate
    -> clear / qualify / hold / block / escalate
Incident Commander, when required
    -> approve / decline
Mission Controller.ActionDispatcher
    -> command
Drone or Boat
    -> action in Flood Environment
Flood Environment
    -> realized observation and outcome
Mission Controller
    -> revision and local repair
```

The external world determines what happened. The world model predicts what might happen. TRACE governs what those predictions are allowed to authorize.
