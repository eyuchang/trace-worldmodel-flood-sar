# Generated vector figures

These SVG files are generated from `configs/scenarios/riverside_flood_v1.yaml` by:

```bash
trace-jepa-visualize --output artifacts/runs/scenario_brief
```

- `operational_cast.svg`: one Mission Controller, two field agents, one Flood Environment, external human authority, and offline evaluation outside the control loop.
- `mission_controller_knowledge.svg`: only the route knowledge available to Mission Control at time zero.
- `simulation_ground_truth.svg`: hidden scenario truth for teaching and post-episode scoring; never an operational input.

Regenerate the figures after changing the scenario or terminology rather than editing the copies by hand.
