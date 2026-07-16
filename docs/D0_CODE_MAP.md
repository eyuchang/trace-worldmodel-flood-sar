# D0.2 Code Map

| Responsibility | Source file |
|---|---|
| Dynamic contracts, path segments, rescue/passenger lifecycle, reasoning cycles, S1-S5 parameters | `src/trace_jepa/workbench/models.py` |
| Initial truth/controller state and edge initialization | `src/trace_jepa/workbench/scenario.py` |
| Route graph, Dijkstra connectors, route-constrained plans | `src/trace_jepa/workbench/navigation.py` |
| Single event reducer, alert counts, pickup/onboard/delivery/standby transitions | `src/trace_jepa/workbench/reducer.py` |
| Hash-chained simulation log | `src/trace_jepa/workbench/store.py` |
| Surrogate prediction, outbound and evacuation candidates, TRACE assessment | `src/trace_jepa/workbench/controller.py` |
| Clock, edge-constrained movement, boarding/unloading schedules, replay, reasoning cycles | `src/trace_jepa/workbench/engine.py` |
| TRACE semantic revisions | `src/trace_jepa/runtime/runtime.py` |
| REST and WebSocket server | `src/trace_jepa/workbench/api.py` |
| `trace-jepa-ui` command | `src/trace_jepa/workbench/cli.py` |
| Browser structure | `src/trace_jepa/workbench/static/index.html` |
| Browser styling | `src/trace_jepa/workbench/static/styles.css` |
| Browser map, controls, reasoning and TRACE views | `src/trace_jepa/workbench/static/app.js` |
| Graph-motion and reasoning tests | `tests/test_navigation_and_reasoning.py` |
| Rescue lifecycle, call-count, and animation contract tests | `tests/test_rescue_lifecycle_and_alert_merge.py` |
| Step-2 verification command | `scripts/verify_step02.sh` |
| Dynamic API and invariant tests | `tests/test_dynamic_workbench.py` |
