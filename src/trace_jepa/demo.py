from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from trace_jepa.contracts import EmergencyCall
from trace_jepa.controller import MissionController
from trace_jepa.runtime import (
    CommitmentLog,
    EvidenceLedger,
    PolicyConfig,
    PolicyEngine,
    TraceRepository,
    TraceRuntime,
)
from trace_jepa.scenario import FloodEnvironment


DEFAULT_SCENARIO = Path("configs/scenarios/riverside_flood_v1.yaml")


def build_runtime(output: Path) -> TraceRuntime:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    return TraceRuntime(
        repository=TraceRepository(output / "records" / "trace.jsonl"),
        ledger=EvidenceLedger(output / "evidence"),
        commitments=CommitmentLog(output / "commitments" / "commitments.jsonl"),
        policy=PolicyEngine(
            PolicyConfig.from_yaml(Path("configs/policies/trace_v1.yaml"))
        ),
    )


def run_demo(
    output: Path,
    *,
    scenario_path: Path = DEFAULT_SCENARIO,
    emergency_call: EmergencyCall | None = None,
    event_sink: Callable[[dict[str, Any]], None] | None = None,
) -> dict:
    output = Path(output)
    runtime = build_runtime(output)
    environment = FloodEnvironment.from_yaml(scenario_path)
    if emergency_call is not None:
        environment.register_emergency_call(emergency_call)
    controller = MissionController(
        environment=environment,
        runtime=runtime,
    )
    return controller.run_episode(output, event_sink=event_sink)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the laptop-safe TRACE-WorldModel flood-SAR Mission Controller demo"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/runs/demo"),
    )
    parser.add_argument(
        "--scenario",
        type=Path,
        default=DEFAULT_SCENARIO,
    )
    args = parser.parse_args()
    summary = run_demo(args.output, scenario_path=args.scenario)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
