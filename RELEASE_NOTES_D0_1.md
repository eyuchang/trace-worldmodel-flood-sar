# D0.1 Release Notes

## Purpose

D0.1 establishes the dynamic, event-sourced shell needed before S1-S5 can be evaluated and before a V-JEPA model is connected.

## Added

- FastAPI and WebSocket server;
- dependency-free browser UI;
- S1-S5 live control tabs;
- controller/truth/difference map views;
- moving asset and group visualization;
- TRACE record inspector;
- live statistics, chart, and immutable event timeline;
- typed `SimulationEvent` contract;
- hash-chained `EventStore`;
- separate `TruthState` and `ControllerState`;
- stochastic observation delivery and sensor error;
- flood/water dynamics and route closure;
- multi-group and multi-asset controls;
- shock injection;
- operator-requested reconnaissance;
- deterministic event replay;
- validated dynamic demonstration and screenshots.

## Test status

```text
22 tests passed
ruff: clean
JavaScript syntax check: clean
```

## Deliberately not claimed

- The surrogate predictor is not V-JEPA.
- The water model is not a hydrological model.
- The UI is not a live emergency-dispatch interface.
- Commander approval is not identity-backed authorization.
- The workbench has not yet run the five-condition experiment.

## Next gate

D1 replaces hand-shaped S1 uncertainty and support quantities with fitted/calibrated estimators and adds paired-seed experimental execution.
