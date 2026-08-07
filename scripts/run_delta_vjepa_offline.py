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

SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the pinned V-JEPA encoder, encode one synchronized offline clip, "
            "and optionally run an unqualified flood head."
        )
    )
    parser.add_argument("--frames", type=Path, required=True, help="Pickle-free NPY [T,H,W,C].")
    parser.add_argument("--observation-id", required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("models/manifests/vjepa2_1_vit_base_384.manifest.json"),
    )
    parser.add_argument("--head", type=Path)
    parser.add_argument("--result", type=Path)
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
    if not arguments.frames.is_file() or arguments.frames.is_symlink():
        raise ValueError("frame input must be a safe regular NPY file")
    frames = np.load(arguments.frames, allow_pickle=False)
    if frames.ndim != 4 or not np.isfinite(frames).all():
        raise ValueError("frames must be a finite four-dimensional array")
    manifest = load_encoder_pin(arguments.manifest)
    checkpoint_metadata = manifest["checkpoint"]
    checkpoint_path = arguments.checkpoint_dir / str(checkpoint_metadata["file_name"])
    encoder = VJEPA2Encoder(checkpoint_dir=arguments.checkpoint_dir)
    if sha256_file(checkpoint_path) != checkpoint_metadata["sha256"]:
        raise ValueError("loaded V-JEPA checkpoint disagrees with the pinned manifest")
    feature = encoder.encode_frames(frames).reshape(-1)
    arguments.cache_dir.mkdir(parents=True, exist_ok=True)
    if arguments.cache_dir.is_symlink():
        raise ValueError("cache directory must not be a symlink")
    observation_sha256 = sha256_file(arguments.frames)
    cache_path = arguments.cache_dir / f"{arguments.observation_id}.npz"
    write_deterministic_feature_cache(
        cache_path,
        feature=feature,
        observation_sha256=observation_sha256,
        encoder_version=str(manifest["encoder_version"]),
        encoder_checkpoint_hash=str(checkpoint_metadata["sha256"]),
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
        if arguments.result is None:
            raise ValueError("--result is required when --head is supplied")
        provider = CachedVJEPAFeatureProvider(
            arguments.cache_dir,
            encoder_version=str(manifest["encoder_version"]),
            encoder_checkpoint_hash=str(checkpoint_metadata["sha256"]),
        )
        head = CalibratedVJEPAHead.load(arguments.head)
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
        arguments.result.parent.mkdir(parents=True, exist_ok=True)
        arguments.result.write_bytes(canonical_json_bytes(summary))
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
