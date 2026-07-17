from __future__ import annotations

import argparse
from pathlib import Path

from trace_jepa.controller import MissionController
from trace_jepa.demo import DEFAULT_SCENARIO, build_runtime
from trace_jepa.intake import EmergencyCallIntake, EmergencyCallIntakeError
from trace_jepa.reporting import format_event, render_timeline_svg, write_timeline_text
from trace_jepa.scenario import FloodEnvironment
from trace_jepa.scenario.visualize import render_map_view, render_operational_cast
from trace_jepa.util import write_json


def _read_call_text(args: argparse.Namespace) -> str:
    if args.call and args.call_file:
        raise EmergencyCallIntakeError("use either --call or --call-file, not both")
    if args.call_file:
        return args.call_file.read_text(encoding="utf-8").strip()
    if args.call:
        return args.call.strip()
    return input("Emergency call: ").strip()


def run_from_emergency_call(args: argparse.Namespace) -> dict:
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    environment = FloodEnvironment.from_yaml(args.scenario)
    call_text = _read_call_text(args)
    call = EmergencyCallIntake(environment.scenario).parse(
        call_text,
        location=args.location,
        people=args.people,
        deadline_minutes=args.deadline_minutes,
        caller_name=args.caller_name,
        caller_contact=args.caller_contact,
    )
    environment.register_emergency_call(call)
    write_json(output / "emergency_call.json", call.model_dump(mode="json"))

    figures = output / "figures"
    render_operational_cast(figures / "operational_cast.svg")
    render_map_view(
        environment.scenario,
        view="mission_controller_knowledge",
        output_path=figures / "mission_controller_knowledge.svg",
    )
    render_map_view(
        environment.scenario,
        view="simulation_ground_truth",
        output_path=figures / "simulation_ground_truth.svg",
    )

    runtime = build_runtime(output)
    controller = MissionController(environment=environment, runtime=runtime)

    if not args.quiet:
        print("\nTRACE-WorldModel flood rescue")
        print("=" * 72)
        print(f"Call:     {call.raw_text}")
        print(f"Location: {call.reported_location} -> {call.normalized_location_id}")
        print(f"People:   {call.people_count}")
        print(f"Deadline: {call.deadline_s // 60} minutes")
        print("-" * 72)

    def event_sink(event: dict) -> None:
        if not args.quiet:
            print(format_event(event))

    summary = controller.run_episode(output, event_sink=event_sink)
    write_timeline_text(summary["timeline"], output / "timeline.txt")
    render_timeline_svg(summary["timeline"], figures / "action_timeline.svg")

    if not args.quiet:
        print("-" * 72)
        print(f"Rescued:           {summary['rescued']}")
        print(f"Record chain valid: {summary['record_chain_valid']}")
        print(f"Summary:           {output / 'summary.json'}")
        print(f"Timeline:          {output / 'timeline.txt'}")
        print(f"Action figure:     {figures / 'action_timeline.svg'}")
        print(f"Controller view:   {figures / 'mission_controller_knowledge.svg'}")

    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Accept an emergency call, ground its location, and run the "
            "TRACE-gated flood-rescue episode."
        )
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--call",
        help=(
            "Emergency call text, for example: "
            "'Four residents are stranded at Riverside Apartments.'"
        ),
    )
    source.add_argument(
        "--call-file",
        type=Path,
        help="UTF-8 text file containing the emergency call",
    )
    parser.add_argument(
        "--location",
        help="Explicit location label when the call text is ambiguous",
    )
    parser.add_argument(
        "--people",
        type=int,
        help="Explicit people count when the call text does not state it",
    )
    parser.add_argument(
        "--deadline-minutes",
        type=int,
        help="Override the scenario's default rescue deadline",
    )
    parser.add_argument("--caller-name")
    parser.add_argument("--caller-contact")
    parser.add_argument(
        "--scenario",
        type=Path,
        default=DEFAULT_SCENARIO,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/runs/emergency_call_demo"),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the live timeline; artifacts are still written",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        run_from_emergency_call(args)
    except (EmergencyCallIntakeError, FileNotFoundError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
