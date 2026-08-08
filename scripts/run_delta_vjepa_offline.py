from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np

from trace_jepa.contracts import ActionInstance, PlanCandidate
from trace_jepa.experimental.profile import AdequacyStatus
from trace_jepa.perception.download import load_encoder_pin
from trace_jepa.perception.vjepa import VJEPA2Encoder
from trace_jepa.predictor import (
    CachedVJEPAFeatureProvider,
    CalibratedVJEPAHead,
    PredictorContext,
    PredictorObservation,
    PredictorPriorProfile,
    PredictorRequest,
    PredictorRouteObservation,
    PredictorVisualFeatureRef,
    VJEPABackedActionPrefixPredictor,
    write_deterministic_feature_cache,
)
from trace_jepa.scenario.delta.artifacts import canonical_json_bytes, sha256_file
from trace_jepa.support import ArtifactLocator, atomic_write_bytes, safe_directory, safe_output_file

SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the pinned V-JEPA encoder, encode one synchronized offline clip, "
            "and optionally run an unqualified flood head."
        )
    )
    parser.add_argument("--frames", type=Path, required=True, help="Pickle-free NPY [T,H,W,C].")
    parser.add_argument("--frames-root", type=Path, required=True)
    parser.add_argument("--observation-id", required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("models/manifests/vjepa2_1_vit_base_384.manifest.json"),
    )
    parser.add_argument("--manifest-root", type=Path, default=Path("models/manifests"))
    parser.add_argument("--head", type=Path)
    parser.add_argument("--head-root", type=Path)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--result-root", type=Path)
    parser.add_argument(
        "--action-type",
        choices=(
            "dispatch_rescue_boat",
            "deploy_ground_team",
            "perform_welfare_check",
            "inspect_levee",
        ),
        default="dispatch_rescue_boat",
    )
    parser.add_argument("--route-id", default="XNG-04")
    return parser


def main() -> None:
    arguments = build_parser().parse_args()
    if not SAFE_IDENTIFIER.fullmatch(arguments.observation_id):
        raise ValueError("observation identifier is unsafe")
    frame_path = ArtifactLocator.from_path(
        root=arguments.frames_root,
        path=arguments.frames,
        maximum_bytes=2_000_000_000,
        label="offline V-JEPA frame array",
    ).resolve()
    frames = np.load(frame_path, allow_pickle=False)
    if frames.ndim != 4 or not np.isfinite(frames).all():
        raise ValueError("frames must be a finite four-dimensional array")
    manifest = load_encoder_pin(arguments.manifest, trusted_root=arguments.manifest_root)
    checkpoint_metadata = manifest["checkpoint"]
    checkpoint_dir = safe_directory(
        arguments.checkpoint_dir,
        declared_root=arguments.checkpoint_dir,
        label="V-JEPA checkpoint directory",
    )
    checkpoint_path = ArtifactLocator(
        root=checkpoint_dir,
        relative_name=Path(str(checkpoint_metadata["file_name"])),
        maximum_bytes=2_000_000_000,
        label="V-JEPA checkpoint",
    ).resolve()
    encoder = VJEPA2Encoder(checkpoint_dir=checkpoint_dir)
    if sha256_file(checkpoint_path) != checkpoint_metadata["sha256"]:
        raise ValueError("loaded V-JEPA checkpoint disagrees with the pinned manifest")
    feature = encoder.encode_frames(frames).reshape(-1)
    cache_dir = safe_directory(
        arguments.cache_dir,
        declared_root=arguments.cache_root,
        label="V-JEPA feature-cache directory",
    )
    observation_sha256 = sha256_file(frame_path)
    cache_path = safe_output_file(
        cache_dir / f"{arguments.observation_id}.npz",
        declared_root=arguments.cache_root,
        label="V-JEPA feature-cache output",
    )
    write_deterministic_feature_cache(
        cache_path,
        feature=feature,
        observation_sha256=observation_sha256,
        encoder_version=str(manifest["encoder_version"]),
        encoder_checkpoint_hash=str(checkpoint_metadata["sha256"]),
        output_root=cache_dir,
    )
    summary: dict[str, object] = {
        "schema_version": "delta-vjepa-offline-execution-v1",
        "qualification_status": "unqualified",
        "scope_note": (
            "Encoder execution demonstrates the governed substitution path; it is not "
            "evidence of Delta flood prediction accuracy."
        ),
        "observation_id": arguments.observation_id,
        "observation_sha256": observation_sha256,
        "feature_cache_sha256": sha256_file(cache_path),
        "feature_dimension": int(feature.size),
        "encoder_manifest_sha256": sha256_file(arguments.manifest),
    }
    if arguments.head is not None:
        if arguments.head_root is None:
            raise ValueError("--head-root is required when --head is supplied")
        if arguments.result is None or arguments.result_root is None:
            raise ValueError("--result and --result-root are required when --head is supplied")
        provider = CachedVJEPAFeatureProvider(
            cache_dir,
            encoder_version=str(manifest["encoder_version"]),
            encoder_checkpoint_hash=str(checkpoint_metadata["sha256"]),
        )
        head = CalibratedVJEPAHead.load(arguments.head, trusted_root=arguments.head_root)
        predictor = VJEPABackedActionPrefixPredictor(
            provider, head, adequacy_status=AdequacyStatus.UNQUALIFIED
        )
        action = ActionInstance(
            action_id="offline-vjepa-action",
            action_type=arguments.action_type,
            actor_id="offline-evaluation-resource",
            origin="FAC-FIRE-01",
            destination="reported-location",
            route_id=arguments.route_id,
        )
        request = PredictorRequest(
            plan=PlanCandidate(
                plan_id="offline-vjepa-plan",
                name="Offline V-JEPA adapter verification",
                actions=(action,),
                utility=1.0,
                reversible_first_action=False,
                requires_authority=True,
            ),
            observation=PredictorObservation(
                routes=[
                    PredictorRouteObservation(
                        route_id=arguments.route_id,
                        report="open",
                        nominal_travel_s=900.0,
                        confidence=0.95,
                    )
                ],
                context=PredictorContext(
                    prior_profile=PredictorPriorProfile(
                        profile_id="delta-prior-high-v1",
                        calibration_version="delta-prior-high-v1-calibration-v1",
                        prior_accuracy_milli=900,
                    ),
                    visual_feature=PredictorVisualFeatureRef(
                        observation_id=arguments.observation_id,
                        observation_sha256=observation_sha256,
                        feature_cache_sha256=sha256_file(cache_path),
                        feature_schema_version="vjepa-frozen-feature-v1",
                        encoder_version=str(manifest["encoder_version"]),
                        encoder_checkpoint_hash=str(checkpoint_metadata["sha256"]),
                        captured_at_s=0,
                    ),
                ),
            ),
        )
        summary["prediction"] = predictor.predict(request).model_dump(mode="json")
        summary["provenance"] = predictor.provenance().model_dump(mode="json")
        result_path = safe_output_file(
            arguments.result,
            declared_root=arguments.result_root,
            label="offline V-JEPA result",
        )
        atomic_write_bytes(
            result_path,
            canonical_json_bytes(summary),
            root=arguments.result_root,
            label="offline V-JEPA result",
        )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
