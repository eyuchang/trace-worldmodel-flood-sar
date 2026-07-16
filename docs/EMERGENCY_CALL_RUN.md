# Run TRACE-JEPA from an Emergency Call

## Input

```text
Emergency. Four residents are stranded at Riverside Apartments.
Flood water is rising and the road is inaccessible.
```

## Command

```bash
trace-jepa-call \
  --call-file examples/calls/riverside_call.txt \
  --output artifacts/runs/call_001
```

Inline equivalent:

```bash
trace-jepa-call \
  --call "Emergency. Four residents are stranded at Riverside Apartments." \
  --output artifacts/runs/call_002
```

## What the program does

1. preserves the raw phone report;
2. normalizes `Riverside Apartments` to `riverside_apartments`;
3. extracts `people_count = 4`;
4. creates the active rescue mission;
5. assesses north dispatch, drone verification, and south dispatch;
6. holds the unsupported north dispatch;
7. dispatches the drone;
8. receives the blocked-route observation;
9. appends a TRACE revision;
10. replans locally and dispatches the boat through the South Detour;
11. records the rescue outcome.

## Outputs

```text
artifacts/runs/call_001/
├── emergency_call.json
├── timeline.txt
├── summary.json
├── records/trace.jsonl
├── evidence/
├── commitments/commitments.jsonl
└── figures/
    ├── operational_cast.svg
    ├── mission_controller_knowledge.svg
    ├── simulation_ground_truth.svg
    └── action_timeline.svg
```

On macOS:

```bash
open artifacts/runs/call_001/figures/mission_controller_knowledge.svg
open artifacts/runs/call_001/figures/action_timeline.svg
```
