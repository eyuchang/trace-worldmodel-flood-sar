# Architecture Map

Start with the operational cast, not the neural network.

```text
                    HUMAN INCIDENT COMMANDER
                    approves dispatch classes
                              |
                              v
+------------------------------------------------------------------+
|                    MISSION CONTROLLER                             |
|              one program at the command post                     |
|                                                                  |
|  Mission State -> Planner -> World Model -> TRACE Gate            |
|       ^                                      |                    |
|       |                                      v                    |
|       +---------------- Action Dispatcher <- decision             |
+------------------------------------------------------------------+
             ^                                      |
             | observations                         | commands
             |                                      v
       +-------------+                        +-------------+
       | Survey Drone|                        | Rescue Boat |
       +-------------+                        +-------------+
             \                                      /
              \                                    /
               +----------------------------------+
               |        FLOOD ENVIRONMENT         |
               | hidden state and consequences    |
               +----------------------------------+
```

The operational system has no separate “evaluator agent.” The Flood Environment owns hidden simulation ground truth. An offline research evaluator may inspect that truth and the logs only after an episode.

## Inside the Mission Controller

```text
reported observations
    |
    v
Mission State
    |
    v
Candidate Planner
    |
    +----------------------------+
    |                            |
    v                            v
World Model                 structural validation
(encoder + action predictor)
    |
    v
Typed semantic claims
    |
    v
WorldModelEvidence ledger
    |
    v
TRACE record and policy gate
    |
    +--> hold / block / escalate
    |
    +--> clear / qualify
              |
              v
       Action Dispatcher
              |
              v
     authorized short action
              |
              v
   Flood Environment outcome
              |
              v
   revision and localized repair
```

## Division of responsibility

| Component | Question answered |
|---|---|
| Flood Environment | What actually happens when an authorized action is applied? |
| Mission State | What has been observed and reported so far? |
| Planner | Which actions are structurally possible? |
| World Model | What might happen under each candidate action? |
| TRACE Gate | May this recorded prediction license this action under the current policy? |
| Incident Commander | Is the organization authorized to make this consequential commitment? |
| Action Dispatcher | Which cleared command is sent to which physical agent? |

The encoder, predictor, probes, policy, scenario, and records are versioned independently. The World Model predicts; the Flood Environment supplies the realized outcome; TRACE controls what may become durable action.
