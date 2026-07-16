# D0.5 Predictive Parallel Scheduling

D0.5 fixes two visible operational defects and replaces lock-step transfer
scheduling with coordinated, TRACE-recorded timing.

Implemented:

- zoom-responsive vehicle marker sizing while retaining exact geographic anchors;
- boats initialized and released at actual transfer-dock graph nodes;
- restored 0.5x, 1x, 2x, 5x, 10x, and 20x simulation-speed control;
- drone verification, boat readiness, and ambulance readiness scheduled in parallel;
- ambulance dispatch begins when the boat picks up patients;
- transfer dock selected by predicted boat, ambulance, and hospital travel time;
- ambulance may arrive first and wait at the selected dock;
- boat may arrive first and wait for the ambulance;
- boat remains available at the selected transfer dock after handoff;
- predicted and actual start/finish times exposed in the UI and TRACE log.
