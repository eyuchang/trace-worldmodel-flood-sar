# Eight-Step Code Map

All files in this side-code pack are exact copies of the repository source at the time the tutorial deck was built. The authoritative paths are under `src/trace_jepa/`; the `Sxx_` names make the deck references easy to follow.

| Step | Responsibility | Authoritative source | Side-file copy | Main functions/classes |
|---|---|---|---|---|
| 1 | Emergency-call intake | `src/trace_jepa/intake.py` | `step01_call_intake/S01_intake.py` | `resolve_location`, `parse_people_count`, `EmergencyCallIntake.parse` |
| 1 | CLI entry point | `src/trace_jepa/emergency_cli.py` | `step01_call_intake/S01_emergency_cli.py` | `run_from_emergency_call`, `build_parser` |
| 2 | Environment and information boundary | `src/trace_jepa/scenario/flood_env.py` | `step02_mission_state/S02_flood_environment.py` | `register_emergency_call`, `observe`, `simulation_ground_truth` |
| 2 | Fused state | `src/trace_jepa/fusion/state.py` | `step02_mission_state/S02_fusion_state.py` | `fuse_state` |
| 2 | Visualizations | `src/trace_jepa/scenario/visualize.py` | `step02_mission_state/S02_visualize.py` | `render_map_view`, `render_operational_cast` |
| 3 | Candidate planner | `src/trace_jepa/planning/planner.py` | `step03_planning/S03_planner.py` | `FloodPlanner.propose`, `FloodPlanner.choose` |
| 3 | Typed action/plan contracts | `src/trace_jepa/contracts/models.py` | `step03_planning/S03_contracts_models.py` | `ActionInstance`, `PlanCandidate` |
| 4 | Deterministic predictive fixture | `src/trace_jepa/predictor/toy.py` | `step04_prediction_claims/S04_toy_predictor.py` | `ToyActionPrefixPredictor.predict` |
| 4 | Latent/prediction-to-claim bridge | `src/trace_jepa/claims/probes.py` | `step04_prediction_claims/S04_claim_probe.py` | `FloodClaimProbe.build_claim` |
| 4-8 | Evidence construction and orchestration | `src/trace_jepa/controller.py` | copies in Steps 6-8 | `_make_evidence`, `_assess_observation`, `run_episode` |
| 5 | Policy gate | `src/trace_jepa/runtime/policy.py` | `step05_trace_gate/S05_policy.py` | `PolicyEngine.evaluate` |
| 5-8 | TRACE runtime | `src/trace_jepa/runtime/runtime.py` | copies in Steps 5-7 | `assess`, `consume`, `revise_with_outcome`, `commit` |
| 5 | Append-only storage | `src/trace_jepa/runtime/storage.py` | `step05_trace_gate/S05_storage.py` | `EvidenceLedger`, `TraceRepository`, `CommitmentLog` |
| 6 | Verification execution | `src/trace_jepa/scenario/flood_env.py` | `step06_verification_dispatch/S06_flood_environment.py` | `execute(verify_route)` |
| 7 | Revision/replanning | `src/trace_jepa/controller.py` | `step07_revision_repair/S07_controller.py` | `run_episode`, lines handling contradiction/replanning |
| 8 | Final rescue and artifacts | `src/trace_jepa/reporting.py`, `emergency_cli.py` | Step 8 copies | `render_timeline_svg`, `write_timeline_text`, `run_from_emergency_call` |

## Exact run command

```bash
trace-jepa-call \
  --call-file examples/calls/riverside_call.txt \
  --output artifacts/runs/call_001
```

## Integrity note

The repository still uses a deterministic toy predictor, a closed location alias registry, a static scenario, a simulated dispatcher, and a deterministic Incident Commander authorization stub. The deck labels each boundary explicitly.
