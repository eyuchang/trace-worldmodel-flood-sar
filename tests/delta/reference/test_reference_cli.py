from __future__ import annotations

from pathlib import Path

import pytest

from trace_reference.cli import build_parser


def test_reference_cli_exposes_run_replay_and_publish() -> None:
    parser = build_parser()

    run = parser.parse_args(["run", "--seed", "20260812", "--output", "run-output"])
    assert run.command == "run"
    assert run.seed == 20260812
    assert run.output == Path("run-output")

    replay = parser.parse_args(
        [
            "replay",
            "--trusted-reference-root",
            "reference-parent",
            "--reference-relative-path",
            "bundle",
            "--output",
            "replay-output",
        ]
    )
    assert replay.command == "replay"
    assert replay.trusted_reference_root == Path("reference-parent")
    assert replay.reference_relative_path == Path("bundle")

    publish = parser.parse_args(
        [
            "publish",
            "--trusted-reference-root",
            "reference-parent",
            "--reference-relative-path",
            "bundle",
            "--output",
            "publication-output",
        ]
    )
    assert publish.command == "publish"
    assert publish.output == Path("publication-output")

    g3 = parser.parse_args(["verify-g3", "--seed", "20260812", "--output", "g3-output"])
    assert g3.command == "verify-g3"

    characterize = parser.parse_args(
        ["characterize-g3", "--seed", "20260812", "--output", "g3-fixtures"]
    )
    assert characterize.command == "characterize-g3"
    assert g3.seed == 20260812

    phase6_core = parser.parse_args(["phase6-core", "--output", "phase6-core"])
    assert phase6_core.command == "phase6-core"
    assert not hasattr(phase6_core, "seed")

    phase6_isolation = parser.parse_args(
        [
            "phase6-isolation",
            "--output",
            "phase6-isolation",
            "--trusted-nominal-root",
            "phase6-core",
            "--nominal-relative-path",
            "nominal",
        ]
    )
    assert phase6_isolation.command == "phase6-isolation"
    assert not hasattr(phase6_isolation, "seed")

    phase6_fault = parser.parse_args(["phase6-fault", "--output", "phase6-fault"])
    assert phase6_fault.command == "phase6-fault"
    assert not hasattr(phase6_fault, "seed")

    phase6_finalize = parser.parse_args(
        [
            "phase6-finalize",
            "--output",
            "phase6-final",
            "--core-root",
            "phase6-core",
            "--core-receipt-relative-path",
            "phase6_core_receipt.json",
            "--isolation-root",
            "phase6-isolation",
            "--isolation-receipt-relative-path",
            "phase6_isolation_receipt.json",
            "--fault-root",
            "g3",
            "--fault-receipt-relative-path",
            "phase6_fault_receipt.json",
            "--g3-handoff-relative-path",
            "data/scenario/delta/reference/g3_handoff_v1/g3_handoff_manifest.json",
        ]
    )
    assert phase6_finalize.command == "phase6-finalize"
    assert not hasattr(phase6_finalize, "seed")


def test_reference_cli_has_no_validation_or_holdout_surface() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["validate"])
    with pytest.raises(SystemExit):
        parser.parse_args(["run", "--seed", "1", "--output", "out", "--study", "holdout"])
