from __future__ import annotations

from pathlib import Path

import pytest

from trace_reference.cli import build_parser


def test_reference_cli_exposes_only_run_and_replay() -> None:
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


def test_reference_cli_has_no_validation_or_holdout_surface() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["validate"])
    with pytest.raises(SystemExit):
        parser.parse_args(["run", "--seed", "1", "--output", "out", "--study", "holdout"])
