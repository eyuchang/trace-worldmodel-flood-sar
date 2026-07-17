# D0.5 Predictive Parallel Scheduling

D0.5 is additive to D0.4. It introduces a new server and UI at `/d05` while
leaving the verified D0.4 workbench available at `/d04`.

## Two visible fixes

1. **Zoom alignment.** Boats and drones begin at transfer-dock graph nodes.
   Their marker sizes shrink as the map zooms out, while the marker anchor
   remains at the exact longitude/latitude.
2. **Time speed control.** The toolbar again exposes 0.5x, 1x, 2x, 5x, 10x,
   20x, and 50x simulation speeds.

## Scheduling change

The mission no longer executes a lock-step chain.

```text
alert received
  -> drone dispatched
  -> probable boat or ambulance prepared concurrently
  -> drone verifies access
  -> prepared response asset departs immediately
  -> boat picks up patients
  -> best transfer dock selected by predicted patient-to-hospital time
  -> ambulance departs for that dock while the boat is still moving
  -> whichever asset arrives first waits
  -> handoff occurs when both are present
  -> ambulance continues to hospital
  -> boat remains on standby at the selected dock
```

## TRACE timing events

D0.5 records:

- `RESPONSE_PREPARATION`
- `SCHEDULE_COMMITTED`
- `SCHEDULE_MILESTONE`
- `TRANSFER_DOCK_SELECTED`
- `AMBULANCE_DISPATCHED_EARLY`
- `AMBULANCE_ARRIVED_EARLY` when applicable
- `PORT_HANDOFF`
- `RENDEZVOUS_HANDOFF_STARTED`
- `SCHEDULE_REVISED` after material parameter or shock changes
- `RESCUE_COMPLETED`

The Reasoning screen displays expected and actual arrival times, the selected
dock, and the predicted rendezvous/hospital time.

## Install

```bash
source "$HOME/miniforge3/etc/profile.d/conda.sh"
conda activate trace-jepa
cd "$HOME/Projects/trace_worldmodel_flood_sar"
python -m pip install -e ".[ui,dev]"
```

## Verify

```bash
./scripts/verify_d05.sh
```

The packaged build has 62 passing Python tests and a successful JavaScript
syntax check. On the CPU-first Mac setup, the optional V-JEPA test may remain
skipped until PyTorch is installed.

## Run

```bash
./scripts/run_d05.sh
```

Open:

```text
http://127.0.0.1:8030/d05
```

## Manual acceptance

1. Zoom out. Boat and drone icons shrink while remaining attached to their
   dock coordinates.
2. Change the Speed selector to 10x and confirm the clock advances faster.
3. Submit a water alarm. Confirm the drone flies while a boat is prepared.
4. After the drone confirms water access, confirm the prepared boat departs.
5. At boat pickup, confirm an ambulance starts toward the selected dock.
6. Confirm the boat does not return to its original embarkation dock.
7. Confirm whichever of boat or ambulance arrives first waits for the other.
8. Confirm the Reasoning tab shows expected and actual timing milestones.
9. Confirm the incident closes only after hospital delivery.
