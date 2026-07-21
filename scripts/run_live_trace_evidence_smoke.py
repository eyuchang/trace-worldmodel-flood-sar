from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from run_live_worldmodel_qualification import (
    build_dinowm_backend,
    build_vjepa_backend,
    environment_manifest,
)
from trace_jepa.util import sha256_file, sha256_value
from trace_jepa.workbench.engine import DynamicRun
from trace_jepa.workbench.models import EventType, EventVisibility, ScenarioLevel
from trace_jepa.worldmodels.live_artifacts import ContentAddressedInferenceStore
from trace_jepa.worldmodels.live_observations import (
    VerifiedSimulatorObservationRepository,
)
from trace_jepa.worldmodels.live_service import LiveInferenceRequest, LiveWorldModelService
from trace_jepa.worldmodels.live_support import LiveSupportingInferenceBridge
from trace_jepa.worldmodels.simulator_observations import (
    SENSOR_MODEL_VERSION,
    SimulatorSensorSnapshot,
    SimulatorVisualObservationStore,
)


def _deliver(run: DynamicRun, captured) -> None:
    run.emit(
        EventType.OBSERVATION,
        source="survey_drone_1",
        scenario_level=ScenarioLevel.S1,
        visibility=EventVisibility.CONTROLLER,
        payload={
            "kind": "route",
            "route_id": "north_channel",
            "reported_status": "open",
            "confidence": 0.9,
            "source": "survey_drone_1",
            "observed_at": 0.0,
            "visual_observation_id": captured.observation_id,
            "visual_observation_hash": captured.observation_hash,
            "visual_observed_at": 0.0,
            "visual_sensor_version": SENSOR_MODEL_VERSION,
        },
    )


def _decision_signature(run: DynamicRun) -> list[dict[str, object]]:
    signatures = []
    seen = set()
    for record in run.runtime.repository.all():
        key = (record.record_id, record.record_version)
        if key in seen or not record.consumer_actions:
            continue
        seen.add(key)
        signatures.append(
            {
                "lineage_key": record.metadata.get("lineage_key"),
                "decision": record.consumer_actions[-1].decision.value,
                "final_status": record.final_status.value,
                "failed_gates": list(record.failed_gates),
            }
        )
    return signatures


def _operational_event_signature(run: DynamicRun) -> list[dict[str, object]]:
    selected = {
        EventType.COMMITMENT_DECISION,
        EventType.PLAN_SELECTED,
        EventType.ACTION_STARTED,
    }
    fields = {
        "plan_id",
        "decision",
        "trace_status",
        "asset_id",
        "action_type",
        "route_id",
        "group_id",
        "truth_safe_at_execution",
        "authorization_outside_tolerance",
    }
    return [
        {
            "event_type": event.event_type.value,
            "payload": {
                key: value for key, value in event.payload.items() if key in fields
            },
        }
        for event in run.event_store.all()
        if event.event_type in selected
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one actual learned-model artifact through TRACE shadow evidence"
    )
    parser.add_argument("--model", choices=("vjepa", "dinowm"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--vjepa-checkpoint-dir", type=Path)
    parser.add_argument("--vjepa-upstream", type=Path)
    parser.add_argument("--dinowm-checkpoint", type=Path)
    parser.add_argument("--dinov2-upstream", type=Path)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError("TRACE live smoke output must be new or empty")
    args.output.mkdir(parents=True, exist_ok=True)

    import torch

    torch.manual_seed(20260766)
    np.random.seed(20260766)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    environment = environment_manifest(args.device)
    environment_sha256 = sha256_value(environment)
    factory_args = SimpleNamespace(**vars(args))
    backend, _ = (
        build_vjepa_backend(factory_args, environment_sha256)
        if args.model == "vjepa"
        else build_dinowm_backend(factory_args, environment_sha256)
    )

    observation_root = args.output / "observations"
    store = SimulatorVisualObservationStore(
        observation_root,
        num_frames=8 if args.model == "vjepa" else 2,
        size=96,
    )
    captured = store.capture(
        SimulatorSensorSnapshot(
            run_id=f"{args.model}-trace-live-smoke",
            episode_id=f"{args.model}-trace-live-development",
            study_partition="development",
            route_id="north_channel",
            asset_id="survey_drone_1",
            observed_at=0.0,
            environment_tick_index=0,
            sensor_seed=20260766,
            water_depth_m=0.35,
            route_closure_depth_m=0.72,
            debris_blocked=False,
            rain_intensity=0.25,
            upstream_inflow=0.20,
            weather_severity=0.25,
            sensor_noise=0.10,
            sensor_quality=0.90,
            packet_delivered=True,
            categorical_report_accurate=True,
            sensor_model_version=SENSOR_MODEL_VERSION,
        )
    )
    repository = VerifiedSimulatorObservationRepository(observation_root)
    inference_store = ContentAddressedInferenceStore(args.output / "inference-store")
    service = LiveWorldModelService(
        backend=backend,
        observation_reader=repository,
        artifact_store=inference_store,
        queue_capacity=8,
    )
    bridge = LiveSupportingInferenceBridge(service=service, observations=repository)
    run = DynamicRun(
        run_id=f"{args.model}-with-live-support",
        scenario_path=args.scenario,
        artifact_root=args.output / "runs",
        supporting_world_model=bridge,
        wait_for_supporting_inference=True,
    )
    _deliver(run, captured)
    run._run_plan_cycle()
    authoritative_with_support = _decision_signature(run)
    operational_with_support = _operational_event_signature(run)
    bridge.close()

    attachments = []
    for path in sorted(run.runtime.ledger.root.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        supporting = payload["reachability_evidence"].get(
            "supporting_worldmodel_inference"
        )
        if supporting is not None:
            attachments.append(supporting)
    if not attachments or any(
        item.get("state") != "completed"
        or item.get("used_for_trace_gate") is not False
        or not item.get("artifact_sha256")
        for item in attachments
    ):
        raise RuntimeError("TRACE evidence ledger lacks a verified supporting artifact")
    persisted_requests = [
        LiveInferenceRequest.model_validate(
            inference_store.get_request(str(item["request_sha256"]))
        )
        for item in attachments
    ]
    if any(
        request.model.bundle_sha256 != backend.identity.bundle_sha256
        for request in persisted_requests
    ):
        raise RuntimeError("persisted request model identity does not match the backend")

    baseline = DynamicRun(
        run_id=f"{args.model}-surrogate-baseline",
        scenario_path=args.scenario,
        artifact_root=args.output / "baseline-runs",
    )
    _deliver(baseline, captured)
    baseline._run_plan_cycle()
    authoritative_baseline = _decision_signature(baseline)
    operational_baseline = _operational_event_signature(baseline)
    if authoritative_with_support != authoritative_baseline:
        raise RuntimeError("supporting inference changed authoritative TRACE decisions")
    if operational_with_support != operational_baseline:
        raise RuntimeError("supporting inference changed operational TRACE behavior")
    event_types = [event.event_type.value for event in run.event_store.all()]
    required = ("OBSERVATION", "PLAN_CYCLE", "TRACE_WRITTEN", "PLAN_SELECTED")
    positions = [event_types.index(item) for item in required]
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        raise RuntimeError("TRACE live smoke violated the required event order")
    chain_verified = run.runtime.repository.verify_chain()
    if not chain_verified:
        raise RuntimeError("TRACE live smoke produced an invalid record chain")
    report = {
        "report_schema_version": "trace-live-support-evidence-smoke-v1",
        "model": args.model,
        "study_partition": "development",
        "test_data_accessed": False,
        "rq_data_accessed": False,
        "model_identity": backend.identity.model_dump(mode="json"),
        "upstream_checkout": backend.upstream_checkout_manifest,
        "environment": environment,
        "environment_manifest_sha256": environment_sha256,
        "observation_id": captured.observation_id,
        "observation_sha256": captured.observation_hash,
        "required_event_order": required,
        "event_types": event_types,
        "supporting_attachments": attachments,
        "persisted_request_hashes": [
            request.request_sha256 for request in persisted_requests
        ],
        "authoritative_decisions_match_surrogate_baseline": True,
        "operational_events_match_surrogate_baseline": True,
        "authoritative_decisions": authoritative_with_support,
        "operational_event_signature": operational_with_support,
        "trace_record_chain_verified": chain_verified,
        "learned_output_used_for_trace_gate": False,
        "scenario": {
            "filename": args.scenario.name,
            "sha256": sha256_file(args.scenario),
            "development_only": True,
        },
        "claim_boundary": (
            "This smoke demonstrates verified observation delivery, learned inference, "
            "and provenance-bound, non-licensing TRACE evidence attachment within one "
            "wait-enabled development plan cycle. The selected operational decision/action "
            "signature matched the surrogate-only baseline. It does not evaluate predictive "
            "quality or change TRACE semantics."
        ),
    }
    report_path = args.output / f"{args.model}_trace_live_evidence_smoke.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    print(f"report={report_path}")
    print(f"report_sha256={sha256_file(report_path)}")


if __name__ == "__main__":
    main()
