# D0.2 Step 3 — MapLibre GeoJSON Operational Map

## Purpose

Checkpoint A proved that a real pitched vector map could load inside the existing
TRACE-JEPA browser shell. Step 3 makes that map operational: routes, graph-edge
status, authorized paths, assets, incidents, hazards, the flood polygon, and the
safe transfer dock are now generated from every WebSocket snapshot as GeoJSON.

The map remains a display layer. It does not calculate navigation. The simulator's
`PathSegment` sequence is authoritative, and the same segments are converted to
GeoJSON for display.

## Console messages seen before this step

- `favicon.ico 404` was harmless. Step 3 adds an inline SVG favicon, so the request
  is no longer made.
- `Expected value to be of type number, but found null instead` was emitted from a
  MapLibre worker/base-style context. The map loaded and the application produced
  no failing stack in `app.js`. All TRACE overlay expressions in Step 3 use
  `coalesce` and typed fallback values so nullable operational fields cannot create
  that warning. A one-time warning from the external base style is non-fatal.
- `Injected script ... shard loaded` is produced by a browser extension/content
  script, not by TRACE-JEPA.

## New source file

`src/trace_jepa/workbench/static/maplibre_overlays.js`

It owns:

- local-coordinate to longitude/latitude conversion;
- GeoJSON feature construction;
- MapLibre source and layer creation;
- controller/truth/difference rendering;
- map selection callbacks;
- short asset-position interpolation between snapshots.

## Operational sources

| Source | Data |
|---|---|
| `trace-flood` | synthetic flood polygon and current water/weather properties |
| `trace-routes` | one feature per navigable route edge |
| `trace-route-labels` | one label point per route |
| `trace-authorized-paths` | the remaining executable `PathSegment` sequence |
| `trace-hazards` | visible or observed route obstructions |
| `trace-incidents` | stranded groups and their waiting/onboard/delivered state |
| `trace-assets` | drones, boats, helicopters, and ground teams |
| `trace-locations` | safe dock and drone pad |

Each WebSocket snapshot calls `GeoJSONSource.setData()`, which causes MapLibre to
re-render the changed source.

## Display georeference

The current Riverside scenario still uses local simulation coordinates. Step 3
uses a versioned display adapter:

```text
origin:          -121.6200, 38.0400
meters per unit: 24
pitch:           55 degrees
bearing:         -18 degrees
```

This is explicitly labeled in the UI as a synthetic display georeference. It is
not yet an imported real waterway network. The planner continues to operate on
local graph nodes and edges.

## View semantics

### Controller

- route colors come from `RouteBelief`;
- hidden blockage coordinates are not shown;
- assets and groups come from controller-visible state.

### Truth

- route-edge colors come from `RouteTruth.edge_open`;
- hidden hazards and truth asset/group state are shown.

### Difference

- mismatches are orange;
- unknown controller state versus known truth is a mismatch;
- the base map does not change, only TRACE-JEPA overlays change.

## Verify

```bash
./scripts/verify_step03.sh
```

Expected on the CPU-first course environment:

```text
3 passed                         # focused overlay tests
35 passed, 1 skipped            # full suite; optional PyTorch seam skipped
JavaScript syntax checks pass
```

If PyTorch is installed, the full suite may report `36 passed` instead.

## Run

```bash
trace-jepa-ui --host 127.0.0.1 --port 8000
open http://127.0.0.1:8000
```

Hard refresh with `Command + Shift + R`.

## Manual acceptance test

1. Confirm the real map loads at a pitched angle.
2. Submit the Riverside emergency call.
3. Confirm the incident marker appears on the real map.
4. Run a reasoning cycle.
5. Confirm North and South route edges use controller-belief colors.
6. Switch to Truth and confirm the hidden blocked edge and hazard appear.
7. Switch to Difference and confirm the mismatch is orange.
8. Start the simulation and watch the drone/boat points move.
9. Confirm the dashed authorized path matches the simulator path.
10. Click a route, asset, or group and confirm the existing inspector updates.

## Exit conditions

- All displayed route segments are generated from route waypoints.
- All displayed authorized paths are generated from `PathSegment` objects.
- No map click changes simulator truth or controller state.
- Controller view does not reveal hidden truth.
- `setData()` updates all operational sources without reloading the map.
- Event and TRACE hash chains remain valid.

## Next step

Step 4 will move the synthetic display reference into the scenario/run manifest,
add map-click incident placement, and introduce actual 3D terrain only after the
GeoJSON overlay contract is stable.
