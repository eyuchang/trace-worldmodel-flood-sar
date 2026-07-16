# Lab 0 - Scenario, entities, and information boundaries

## Goal

Understand the flood-rescue mission before writing code.

## Read

- `docs/SCENARIO_BRIEF.md`
- `docs/ENTITY_MODEL.md`
- `docs/ARCHITECTURE.md`

## Tasks

1. Name every operational entity and software module.
2. State who initially knows the North Channel is blocked.
3. Explain that the drone is a sensor-bearing field agent and that offline scoring occurs only after the episode.
4. Explain who calls TRACE.
5. Explain the difference between a model prediction, a TRACE technical decision, and human authorization.
6. Render the mission-controller and simulation-ground-truth views.

## Commands

```bash
trace-jepa-visualize --output artifacts/runs/lab00_views
```

## Exit test

A student can narrate the complete episode, from partial observation to revision, while keeping hidden simulation state out of MissionState.
