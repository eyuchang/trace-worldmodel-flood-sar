from __future__ import annotations

import json
import re
from pathlib import Path

from trace_jepa.experimental.profile import AdequacyStatus
from trace_jepa.predictor import ToyActionPrefixPredictor
from trace_jepa.scenario.delta.cli import _defaults, build_parser
from trace_jepa.scenario.delta.loading import load_acceptance_config, load_scenario_config

ROOT = Path(__file__).resolve().parents[3]
README = ROOT / "README.md"
DELTA_DOCS = (
    ROOT / "docs/delta/WF_DFLD_01_SMALL.md",
    ROOT / "docs/delta/WF_DFLD_01_SMALL_V10_PROTOCOL.md",
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


def test_readme_matches_v10_default_contract_and_environment() -> None:
    payload = README.read_text("utf-8")
    defaults = _defaults()
    assert all(defaults[name].is_file() for name in ("config", "geography", "policy"))
    config = load_scenario_config(defaults["config"])
    contract = json.loads(
        (ROOT / "data/scenario/delta/environment/python311_linux_amd64_v1.json").read_text("utf-8")
    )
    assert config.generator_version == "delta-small-generator-v8"
    if defaults["acceptance"].is_file():
        acceptance = load_acceptance_config(defaults["acceptance"])
        assert acceptance.schema_version == "delta-small-acceptance-v10"
        assert defaults["scientific_manifest"].is_file()
    else:
        assert not defaults["scientific_manifest"].is_file()
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
    for field_name in (
        "peak_finite_strict_concurrent_load_ratio_milli",
        "peak_finite_uncapped_compatible_load_ratio_milli",
        "peak_finite_registered_normalized_coverable_load_index_milli",
        "peak_finite_residual_strict_pressure_ratio_milli",
    ):
        assert field_name in README.read_text("utf-8")


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


def test_readme_development_values_match_the_canonical_report() -> None:
    report = json.loads(
        (ROOT / "docs/delta/validation/WF_DFLD_01_SMALL_DEVELOPMENT_V6.json").read_text("utf-8")
    )
    study = report["study"]
    readme = README.read_text("utf-8")
    interval_separator = "\N{EN DASH}"
    assert report["execution_role"] == "development"
    assert report["confirmatory_seeds_accessed"] is False
    call_count = study["call_count"]
    assert (
        f"| Observed calls per seed | {call_count['estimate']:.2f} | "
        f"{call_count['lower_95']:.2f}{interval_separator}{call_count['upper_95']:.2f} |"
    ) in readme
    hour_four = study["call_count"]["hourly_mean_95"][3]
    assert (
        f"| Hour-four calls per seed | {hour_four['estimate']:.2f} | "
        f"{hour_four['lower_95']:.2f}{interval_separator}{hour_four['upper_95']:.2f} |"
    ) in readme
    strict = study["peak_finite_strict_concurrent_load_ratio"]
    assert f"| Finite strict-load median | {strict['estimate']:.2f} |" in readme
    operations = study["operations"]
    assert (
        "| Allocations / refusals / repairs per seed | "
        f"{operations['allocations']['estimate']:.2f} / "
        f"{operations['refusals']['estimate']:.2f} / "
        f"{operations['repairs']['estimate']:.2f} |"
    ) in readme
    paired = report["paired_reconciliation"]["metrics"]
    for label, metric_name in (
        ("Selected-minus-baseline false-merge rate", "false_merge_rate"),
        ("Selected-minus-baseline pairwise recall", "pairwise_recall"),
    ):
        metric = paired[metric_name]["paired_difference_selected_minus_baseline"]
        estimate = f"{metric['estimate']:.3f}".replace("-", "\N{MINUS SIGN}")
        lower = f"{metric['lower_95']:.3f}".replace("-", "\N{MINUS SIGN}")
        upper = f"{metric['upper_95']:.3f}".replace("-", "\N{MINUS SIGN}")
        rendered = f"| {label} | {estimate} | {lower}{interval_separator}{upper} |"
        assert rendered in readme
    adverse = paired["false_report_merge_rate"]["paired_difference_selected_minus_baseline"]
    normalized_readme = " ".join(readme.split())
    adverse_lower = f"{adverse['lower_95']:.3f}".replace("-", "\N{MINUS SIGN}")
    assert (
        f"+{adverse['estimate']:.3f} development difference in false-report merge "
        f"rate (95% interval {adverse_lower} to "
        f"+{adverse['upper_95']:.3f})"
    ) in normalized_readme


def test_documented_delta_commands_cannot_accidentally_execute_holdout() -> None:
    payloads = [README.read_text("utf-8"), *[path.read_text("utf-8") for path in DELTA_DOCS]]
    joined = "\n".join(payloads)
    assert "--model" not in README.read_text("utf-8")
    assert "/tmp" not in joined
    assert "authoritative offline geography" not in joined.lower()
    assert "--study original-confirmatory" not in README.read_text("utf-8")
    assert "confirmatory-v7 execution" not in README.read_text("utf-8")
    readme = README.read_text("utf-8")
    assert "wf-dfld-01-small-confirmatory-v8-original-r2" not in readme
    assert "wf-dfld-01-small-confirmatory-v8-recovery-replication-v1" not in readme
    assert "wf-dfld-01-small-confirmatory-v8-artifact-reconstruction-replication-v1" in readme
    assert "artifact-reconstruction-replication" in readme.lower()
    assert "cannot be described as untouched confirmatory evidence" in " ".join(readme.split())
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
            "legacy-original.json",
            "--output",
            "legacy-replication.json",
        ]
    )
    parser.parse_args(
        [
            "validate",
            "--study",
            "replication",
            "--registered-evidence-report",
            "original.json",
            "--output",
            "replication.json",
        ]
    )
    assert "--pin-manifest" in README.read_text("utf-8")
    assert "--receipt" in README.read_text("utf-8")
    assert "--checkpoint-dir" in README.read_text("utf-8")
    assert "--frames-root" in README.read_text("utf-8")
    assert "--cache-root" in README.read_text("utf-8")


def test_current_methodology_matches_executed_generation_order() -> None:
    methodology = (ROOT / "docs/delta/WF_DFLD_01_SMALL.md").read_text("utf-8")
    assert (
        "geography → meteorology → hydrology → crossing state → truth → observations →\n"
        "coordination → resources → predictor prior"
    ) in methodology
