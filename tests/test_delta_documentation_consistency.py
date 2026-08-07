from __future__ import annotations

import json
import re
from pathlib import Path

from trace_jepa.experimental.profile import AdequacyStatus
from trace_jepa.predictor import ToyActionPrefixPredictor
from trace_jepa.scenario.delta.cli import _defaults
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


def test_readme_matches_v7_default_contract_and_environment() -> None:
    payload = README.read_text("utf-8")
    defaults = _defaults()
    assert all(path.is_file() for path in defaults.values())
    config = load_scenario_config(defaults["config"])
    acceptance = load_acceptance_config(defaults["acceptance"])
    contract = json.loads(
        (ROOT / "data/scenario/delta/environment/python311_linux_amd64_v1.json").read_text("utf-8")
    )
    assert config.generator_version == "delta-small-generator-v7"
    assert acceptance.schema_version == "delta-small-acceptance-v7"
    assert "delta-small-generator-v7" in (ROOT / "docs/delta/WF_DFLD_01_SMALL.md").read_text(
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


def test_delta_docs_use_v7_metric_and_reconciliation_labels() -> None:
    joined = "\n".join(path.read_text("utf-8") for path in DELTA_DOCS)
    assert "strict concurrent load" in joined.lower()
    assert "registered_normalized_coverable_load_index" in joined
    assert "pairwise precision" in joined
    assert "adjusted Rand" in joined
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
