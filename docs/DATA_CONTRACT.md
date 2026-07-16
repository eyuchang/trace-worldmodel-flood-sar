# Flood-SAR Trajectory Data Contract

A trajectory window is a versioned training and evaluation unit. It must not mix simulation-ground-truth fields into the Mission Controller input.

## Required fields

```yaml
episode_id: string
window_id: string
start_time: ISO-8601
end_time: ISO-8601
platforms:
  - platform_id: string
    platform_type: drone | rescue_boat | ground_team | support_vehicle
    sensor_refs: [string]
    telemetry_ref: string
observation:
  video_ref: string
  frame_indices: [int]
  observation_hash: string
  freshness_s: float
map_ref: string
mission_state_ref: string
communication_state_ref: string
action_prefix:
  schema_version: string
  actions:
    - action_id: string
      actor_id: string
      parameters: object
realized_future:
  horizon_steps: int
  route_open: object
  arrival_time_s: object
  hazard_score: object
  resource_margin: object
provenance:
  source: string
  collection_protocol: string
  preprocessing_version: string
  split: train | validation | calibration | test
```

## Rules

1. `realized_future` is a label and may not enter the fused state.
2. Every time series must use one declared clock and time alignment policy.
3. Every coordinate must name its frame and units.
4. Every action must conform to a versioned action schema.
5. Calibration and test episodes must be disjoint from training at the scenario level where possible.
6. A model manifest must name the exact dataset snapshot and preprocessing version.
