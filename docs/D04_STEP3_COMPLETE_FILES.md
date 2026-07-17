# D0.4 Step 3 and Later: Complete Files, No Manual Block Replacement

This release is additive. It does not require editing pieces inside the earlier
D0.2/D0.3 files.

Complete files supplied:

- `configs/geography/antioch_delta_real_v1.yaml`
- `src/trace_jepa/workbench/geography_builder.py`
- `src/trace_jepa/workbench/real_geography.py`
- `src/trace_jepa/workbench/d04_server.py`
- `src/trace_jepa/workbench/d04_static/index.html`
- `tests/test_d04_real_geography.py`
- `tests/fixtures/d04_geography/*`
- `scripts/build_d04_geography.sh`
- `scripts/verify_d04.sh`
- `scripts/run_d04.sh`

The D0.4 workbench uses:

- real OpenStreetMap waterway centerlines for boat routing;
- real OpenStreetMap roads for ambulance routing;
- a selected river transfer port and hospital;
- three docked drones that fly only for declared alarm tasks;
- two boats and two ambulances;
- TRACE-gated assignment, preemption, port handoff, and completion;
- map-click longitude/latitude without local x/y entry.

## Install

```bash
source "$HOME/miniforge3/etc/profile.d/conda.sh"
conda activate trace-jepa

cd "$HOME/Projects/trace_worldmodel_flood_sar"

python -m pip install -e ".[ui,dev]"
```

## Build the cached real geography once

```bash
./scripts/build_d04_geography.sh
```

The script queries Overpass and writes a versioned, hash-recorded geography
snapshot to:

```text
data/geography/antioch_delta_real_v1/
```

The simulator does not query OpenStreetMap during each run.

## Verify

```bash
./scripts/verify_d04.sh
```

The focused D0.4 suite contains ten tests. The full repository suite is also
run. The optional V-JEPA test may remain skipped until PyTorch is installed.

## Run

```bash
./scripts/run_d04.sh
```

Open:

```text
http://127.0.0.1:8020/d04
```

## Expected operational flow

```text
map-clicked alert
    -> nearest available drone verifies exact alarm coordinate
    -> drone returns to its riverside base
    -> access is classified from real water and road graphs
    -> boat or ambulance is assigned
    -> water patients go to the selected river transfer port
    -> ambulance moves them from port to hospital
    -> incident completes only after hospital handoff
```

## Preemption demo

Press **Run preemption demo**.

- Boat 2 is grounded.
- Boat 1 begins a moderate-priority water mission.
- A critical water incident appears twelve simulated seconds later.
- TRACE records the priority comparison.
- Boat 1 changes task only at the next real water-network node.
- A carrying boat or ambulance is never preempted.

## Scientific boundary

The downloaded OSM geometry supplies real centerlines and graph connectivity.
It does not prove that every segment is navigable for every rescue boat.
Dynamic depth, debris, current, congestion, and weather remain simulator state
and TRACE evidence.
