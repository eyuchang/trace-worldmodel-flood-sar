# Core source file map for the first implementation block

Use this map when a slide says "see side file" or "see source".

| Stage | Concept | Primary source files |
|---|---|---|
| 0 | Operational cast and information boundary | `docs/MISSION_BRIEF.md`, `docs/ENTITY_MODEL.md` |
| 1 | Setup and project verification | `pyproject.toml`, `src/trace_jepa/verify.py` |
| 2 | Scenario visualization | `src/trace_jepa/scenario/visualize.py`, `configs/scenarios/riverside_flood_v1.yaml` |
| 3 | Scenario dynamics | `src/trace_jepa/scenario/flood_env.py` |
| 4 | Durable contracts | `src/trace_jepa/contracts/models.py` |
| 5 | Append-only storage | `src/trace_jepa/runtime/storage.py` |
| 6 | Technical policy gate | `configs/policies/trace_v1.yaml`, `src/trace_jepa/runtime/policy.py` |
| 7 | Emergency-call intake | `src/trace_jepa/intake.py`, `src/trace_jepa/emergency_cli.py` |
| 8 | Closed-loop Mission Controller | `src/trace_jepa/controller.py`, `src/trace_jepa/demo.py` |
| 9 | Planner and mock predictor | `src/trace_jepa/planning/planner.py`, `src/trace_jepa/predictor/toy.py` |

The first deck uses deterministic fixtures. They are for teaching and regression tests. They are not experimental results.
