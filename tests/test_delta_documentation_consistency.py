from __future__ import annotations

import json
import re
from pathlib import Path

from trace_jepa.experimental.profile import AdequacyStatus
from trace_jepa.predictor import ToyActionPrefixPredictor
from trace_jepa.scenario.delta.cli import _defaults, build_parser
from trace_jepa.scenario.delta.loading import load_acceptance_config, load_scenario_config

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
DELTA_DOCS = (
    ROOT / "docs/delta/WF_DFLD_01_SMALL.md",
    ROOT / "docs/delta/GEOGRAPHY_DATA_CARD.md",
    ROOT / "docs/delta/HYDROLOGY_MODEL_CARD.md",
    ROOT / "docs/delta/OBSERVATION_AND_CAPACITY_PROTOCOL.md",
    ROOT / "docs/delta/PREDICTOR_QUALIFICATION.md",
)


def test_readme_relative_markdown_links_resolve() -> None:
    payload = README.read_text("utf-8")
    for target in re.findall(r"\]\(([^)]+)\)", payload):
        if target.startswith(("http://", "https://", "#")):
            continue
        relative = target.split("#", maxsplit=1)[0]
        assert (ROOT / relative).exists(), f"README link does not resolve: {target}"


def test_readme_matches_v8_default_contract_and_environment() -> None:
    payload = README.read_text("utf-8")
    defaults = _defaults()
    assert all(path.is_file() for path in defaults.values())
    config = load_scenario_config(defaults["config"])
    acceptance = load_acceptance_config(defaults["acceptance"])
    contract = json.loads(
        (ROOT / "data/scenario/delta/environment/python311_linux_amd64_v1.json").read_text("utf-8")
    )
    assert config.generator_version == "delta-small-generator-v8"
    expected_acceptance = (
        "delta-small-acceptance-v8"
        if (ROOT / "configs/scenarios/wf_dfld_01_small_acceptance_v4.yaml").is_file()
        else "delta-small-acceptance-v7"
    )
    assert acceptance.schema_version == expected_acceptance
    assert "delta-small-generator-v8" in (ROOT / "docs/delta/WF_DFLD_01_SMALL.md").read_text(
        "utf-8"
    )
    assert contract["oci_platform_manifest_sha256"] in payload
    assert "requirements-delta-python311.lock" in payload
    assert "delta_small_geography_v3.yaml" in str(defaults["geography"])
    assert "v2-fleet-map" not in payload


def test_documented_predictor_status_matches_runtime_provenance() -> None:
    readme = README.read_text("utf-8")
    predictor_doc = (ROOT / "docs/delta/PREDICTOR_QUALIFICATION.md").read_text("utf-8")
    toy = ToyActionPrefixPredictor().provenance()
    assert toy.adequacy_status == AdequacyStatus.QUALIFIED
    assert "Toy" in predictor_doc and "`QUALIFIED` teaching fixture" in predictor_doc
    assert "MLP and V-JEPA are **unqualified**" in readme
    assert "MLP" in predictor_doc and "V-JEPA-backed" in predictor_doc
    assert predictor_doc.count("`UNQUALIFIED`") >= 2


def test_delta_docs_use_v8_metric_reconciliation_and_censoring_labels() -> None:
    joined = "\n".join(path.read_text("utf-8") for path in DELTA_DOCS)
    assert "strict concurrent load" in joined.lower()
    assert "registered_normalized_coverable_load_index" in joined
    assert "pairwise precision" in joined
    assert "adjusted Rand" in joined
    assert "evidence-graph-q075" in joined
    assert "active_at_scenario_censoring" in joined
    assert "reported_occupant_revision_truth_accuracy" in joined
    assert "gross compatible scenario load" not in (
        ROOT / "docs/delta/OBSERVATION_AND_CAPACITY_PROTOCOL.md"
    ).read_text("utf-8")


def test_readme_historical_1_5_label_is_supported_by_immutable_table() -> None:
    table = json.loads(
        (ROOT / "docs/delta/figures/wf_dfld_01_small_v2/publication_result_table.json").read_text(
            "utf-8"
        )
    )
    assert table["book_walkthrough"]["peak_gross_compatible_load_ratio_milli"] == 1500
    payload = " ".join(README.read_text("utf-8").split())
    assert "historical `registered_normalized_coverable_load_index`" in payload
    assert "v6 value of 1.5" in payload


def test_documented_delta_commands_cannot_accidentally_execute_holdout() -> None:
    payloads = [README.read_text("utf-8"), *[path.read_text("utf-8") for path in DELTA_DOCS]]
    joined = "\n".join(payloads)
    assert "--model" not in README.read_text("utf-8")
    assert "/tmp" not in joined
    assert "authoritative offline geography" not in joined.lower()
    assert "--study original-confirmatory" not in README.read_text("utf-8")
    for block in re.findall(r"```bash\n(.*?)```", joined, flags=re.DOTALL):
        if "trace-jepa-delta-small validate" in block:
            assert "--study" in block


def test_documented_delta_cli_options_are_current() -> None:
    parser = build_parser()
    parser.parse_args(
        [
            "validate",
            "--study",
            "development",
            "--output",
            "development.json",
        ]
    )
    parser.parse_args(
        [
            "validate",
            "--study",
            "replication",
            "--original-report",
            "original.json",
            "--output",
            "replication.json",
        ]
    )
    assert "--pin-manifest" in README.read_text("utf-8")
    assert "--receipt" in README.read_text("utf-8")
    assert "--checkpoint-dir" in README.read_text("utf-8")
