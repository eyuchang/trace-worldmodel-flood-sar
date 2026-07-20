from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from trace_jepa.workbench.api import create_app
from trace_jepa.worldmodels.factory import (
    build_cached_dinowm_route_model,
    build_cached_vjepa_route_model,
)
from trace_jepa.worldmodels.simulator_observations import SimulatorVisualObservationStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the TRACE-WorldModel dynamic Flood-SAR UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--scenario", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--jepa-head", type=Path)
    parser.add_argument("--jepa-feature-cache", type=Path)
    parser.add_argument("--dinowm-head", type=Path)
    parser.add_argument("--dinowm-feature-cache", type=Path)
    parser.add_argument("--visual-observation-dir", type=Path)
    args = parser.parse_args()
    jepa_values = (args.jepa_head, args.jepa_feature_cache, args.visual_observation_dir)
    dinowm_values = (
        args.dinowm_head,
        args.dinowm_feature_cache,
        args.visual_observation_dir,
    )
    if any(value is not None for value in jepa_values) and not all(
        value is not None for value in jepa_values
    ):
        parser.error(
            "--jepa-head, --jepa-feature-cache, and --visual-observation-dir "
            "must be supplied together"
        )
    if any(value is not None for value in dinowm_values) and not all(
        value is not None for value in dinowm_values
    ):
        parser.error(
            "--dinowm-head, --dinowm-feature-cache, and --visual-observation-dir "
            "must be supplied together"
        )
    if args.jepa_head is not None and args.dinowm_head is not None:
        parser.error("configure only one route world-model adapter at a time")
    if args.reload and (
        all(value is not None for value in jepa_values)
        or all(value is not None for value in dinowm_values)
        or args.scenario is not None
        or args.artifact_root is not None
    ):
        parser.error("--reload cannot preserve custom in-process run configuration")
    if args.reload:
        application = "trace_jepa.workbench.api:app"
    elif args.jepa_head is not None:
        route_world_model = build_cached_vjepa_route_model(
            args.jepa_head,
            args.jepa_feature_cache,
        )
        visual_store = SimulatorVisualObservationStore(
            args.visual_observation_dir,
            num_frames=16,
            size=96,
            frame_step=4,
        )
        application = create_app(
            scenario_path=args.scenario,
            artifact_root=args.artifact_root,
            route_world_model=route_world_model,
            visual_observation_store=visual_store,
        )
    elif args.dinowm_head is not None:
        route_world_model = build_cached_dinowm_route_model(
            args.dinowm_head,
            args.dinowm_feature_cache,
        )
        visual_store = SimulatorVisualObservationStore(
            args.visual_observation_dir,
            num_frames=2,
            size=96,
        )
        application = create_app(
            scenario_path=args.scenario,
            artifact_root=args.artifact_root,
            route_world_model=route_world_model,
            visual_observation_store=visual_store,
        )
    else:
        application = create_app(
            scenario_path=args.scenario,
            artifact_root=args.artifact_root,
        )
    uvicorn.run(
        application,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
