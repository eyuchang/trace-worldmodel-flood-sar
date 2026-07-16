# Lab 2 - TRACE-gated rescue without JEPA

## Mission

Four residents are waiting at Riverside Apartments. The rescue boat starts at the Rescue Base. The North Channel is faster but unverified. The South Detour is slower but reported open. Hidden simulation truth says the North Channel is blocked.

## Goal

Close the accountability loop with deterministic components before adding a large encoder.

## What the central program does

The `MissionController`:

1. reads the current observation from the Flood Environment;
2. asks the Planner for grounded candidate actions;
3. asks the toy World Model for predictions;
4. turns predictions into claims;
5. calls the TRACE Gate;
6. dispatches only a cleared or qualified action;
7. attaches the environment outcome;
8. repairs only the dependent branch.

## Tasks

1. Run the vector scenario briefing.
2. Run the mock episode.
3. Locate the north-route values:
   - predicted plan success `0.92`;
   - claim confidence `0.92`;
   - model support `0.28`;
   - OOD score `0.82`.
4. Explain why `north-direct` is held despite its numerical prediction.
5. Confirm that `verify-north` is the first selected action.
6. Confirm that the drone report changes Mission Controller knowledge from `unknown` to `blocked`.
7. Confirm that the old prediction remains and a new revision rejects it.
8. Confirm that `south-detour` names `rescue_boat_1`, the destination, route, residents, and deadline.
9. Confirm that the final commitment cites its own authorizing record version.

## Commands

```bash
trace-jepa-visualize --output artifacts/runs/lab02_brief
trace-jepa-demo --output artifacts/runs/lab02
cat artifacts/runs/lab02/summary.json
pytest tests/test_policy.py tests/test_end_to_end.py
```

## Exit test

The run contains a held unsupported north dispatch, a cleared information-gathering action, an append-only revision, and a locally repaired south dispatch.
