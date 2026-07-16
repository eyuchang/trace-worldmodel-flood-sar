# D0.4 Release Notes

D0.4 replaces synthetic display routing with cached real OpenStreetMap
geography while leaving D0.2/D0.3 available for regression comparison.

Implemented:

- real waterway graph and thin navigation-centerline overlay;
- real road graph for ambulances;
- map-click incident coordinates stored directly as longitude/latitude;
- three docked drones dispatched only to alarm locations;
- two independently located boats;
- two hospital ambulances;
- river-port-to-hospital transfer chain;
- multi-asset scheduling and TRACE-gated preemption;
- non-preemptibility while carrying passengers or patients;
- complete task, lifecycle, TRACE, and activity displays;
- deterministic fixture tests independent of network access.

The geography build is a one-time, versioned operation. Run artifacts retain
the OSM source, Overpass endpoint, configuration hash, and raw-response hashes.
