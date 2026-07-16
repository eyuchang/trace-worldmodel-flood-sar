from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from trace_jepa.workbench.engine import DynamicRun


async def run_demo(output: Path, *, steps: int, dt: float) -> DynamicRun:
    repo_root = Path(__file__).resolve().parents[3]
    run = DynamicRun(
        scenario_path=repo_root / "configs" / "scenarios" / "riverside_flood_v1.yaml",
        artifact_root=output,
    )
    for _ in range(steps):
        await run.step(dt)
    run.export_manifest()
    snapshot = run.snapshot().model_dump(mode="json")
    (run.artifact_root / "final_snapshot.json").write_text(
        json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8"
    )
    timeline = [
        f"{event.simulation_time:7.1f}s  {event.event_type.value:24s}  {event.payload}"
        for event in run.event_store.all()
    ]
    (run.artifact_root / "timeline.txt").write_text("\n".join(timeline) + "\n", encoding="utf-8")
    return run


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a deterministic dynamic Flood-SAR episode")
    parser.add_argument("--output", type=Path, default=Path("artifacts/dynamic_demo"))
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--dt", type=float, default=5.0)
    args = parser.parse_args()
    run = asyncio.run(run_demo(args.output, steps=args.steps, dt=args.dt))
    print(f"Run ID: {run.run_id}")
    print(f"Simulation time: {run.state.truth.simulation_time:.1f} s")
    print(f"Rescued people: {run.state.metrics.rescued_people}")
    print(f"TRACE records: {run.state.metrics.trace_records}")
    print(f"Revisions: {run.state.metrics.revisions}")
    print(f"Event chain valid: {run.event_store.verify_chain()}")
    print(f"TRACE chain valid: {run.runtime.repository.verify_chain()}")
    print(f"Artifacts: {run.artifact_root}")


if __name__ == "__main__":
    main()
