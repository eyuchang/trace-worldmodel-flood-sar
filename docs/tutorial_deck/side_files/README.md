# TRACE-WorldModel flood-rescue tutorial deck side files

The PowerPoint deck contains every short command block and every code fragment needed to explain the first implementation stages. Longer files are stored here and referenced by slide number and side-file label.

## How to use these files

1. Start with the deck.
2. When a slide says `Side file S05`, open the matching file in this folder.
3. Copy lab scripts from `lab_scripts/` into the repository or run the versions already present under `labs/`.
4. Treat `complete_source/` as read-only reference copies of the implementation source.

## Side-file index

| Label | File | Purpose |
|---|---|---|
| S00 | `S00_environment_setup.sh` | Ground-zero Conda/Python setup |
| S01 | `S01_install_and_verify.sh` | Editable install, verifier, test suite |
| S02 | `S02_visualize_environment.sh` | Render operational cast and map views |
| S03 | `S03_riverside_flood_v1.yaml` | Scenario geometry, route status, assets, mission |
| S04 | `S04_flood_actions_v1.yaml` | Grounded action schema |
| S05 | `lab_scripts/S05_first_trace_record.py` | First evidence object and TRACE record |
| S06 | `lab_scripts/S06_policy_walkthrough.py` | Four policy-gate cases |
| S07 | `S07_run_mock_closed_loop.sh` | Deterministic end-to-end demo |
| S08 | `S08_core_source_file_map.md` | Where each implementation concept lives |

## Complete source copies

The `complete_source/` folder contains longer source files copied from `src/trace_jepa/` so the deck can cite them without placing hundreds of lines on slides.

## Emergency-call entry point

| Label | File | Purpose |
|---|---|---|
| S09 | `S09_emergency_call.txt` | Example emergency phone report with location and people count |
| S10 | `S10_run_emergency_call.sh` | One-command call-to-rescue run |
| S10 source | `complete_source/S10_emergency_call_intake.py` | Deterministic location and people grounding |
| S11 source | `complete_source/S11_emergency_call_cli.py` | `trace-jepa-call` terminal entry point |
| S12 source | `complete_source/S12_timeline_reporting.py` | Text and SVG timeline writer |
| S13 source | `complete_source/S13_mission_controller_with_timeline.py` | Controller emitting subsequent actions |
