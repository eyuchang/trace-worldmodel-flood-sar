from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from trace_reference import (
    REFERENCE_PROTOCOL,
    derive_study_seed,
    load_reference_config,
    load_reference_governance,
    load_reference_source_requirements,
    load_reference_source_research,
    verify_small_baseline,
)
from trace_reference.loading import ReferenceConfigurationError
from trace_reference.models import REFERENCE_GENERATION_ORDER
from trace_reference.seeds import derive_seed_prefix

ROOT = Path(__file__).resolve().parents[3]
CONFIG = Path("configs/scenarios/wf_dfld_01_reference_development.yaml")
GOVERNANCE = Path("configs/governance/wf_dfld_01_reference_governance_v1.yaml")
SOURCES = Path("data/scenario/delta/reference/sources/requirements_v1.yaml")
SOURCE_RESEARCH = Path("data/scenario/delta/reference/sources/source_research_v1.yaml")
BASELINE = Path("data/scenario/delta/reference_protocol/small_baseline_v1.json")


def test_reference_development_contract_is_explicit_and_nonconfirmatory() -> None:
    config = load_reference_config(ROOT, CONFIG)
    assert config.status == "design-draft-development-only"
    assert config.timeline.burn_in_start_s == -172_800
    assert config.timeline.evaluation_end_s == 345_600
    assert config.process_targets.breach_time_s == 187_200
    assert config.extent.synthetic_people == 1_400
    assert config.generation_order == REFERENCE_GENERATION_ORDER
    assert REFERENCE_PROTOCOL.generation_order == REFERENCE_GENERATION_ORDER
    payload = yaml.safe_load((ROOT / CONFIG).read_text("utf-8"))
    assert "confirmatory" not in payload["study_namespaces"]
    assert "confirmatory_seeds" not in json.dumps(payload).lower()


def test_reference_config_rejects_scope_and_holdout_substitution(tmp_path: Path) -> None:
    payload = yaml.safe_load((ROOT / CONFIG).read_text("utf-8"))
    payload["extent"]["synthetic_people"] = 1_399
    altered = tmp_path / "altered.yaml"
    altered.write_text(yaml.safe_dump(payload, sort_keys=False), "utf-8")
    with pytest.raises(ReferenceConfigurationError, match="design contract"):
        load_reference_config(tmp_path, Path("altered.yaml"))

    payload = yaml.safe_load((ROOT / CONFIG).read_text("utf-8"))
    payload["study_namespaces"]["confirmatory"] = {
        "namespace": "WF-DFLD-01-REFERENCE|confirmatory-v1|index",
        "materialized": False,
    }
    altered.write_text(yaml.safe_dump(payload, sort_keys=False), "utf-8")
    with pytest.raises(ReferenceConfigurationError, match="design contract"):
        load_reference_config(tmp_path, Path("altered.yaml"))


def test_reference_study_seed_surface_excludes_confirmation() -> None:
    development = derive_seed_prefix("development", 100)
    selection = derive_seed_prefix("selection", 100)
    validation = derive_seed_prefix("validation", 100)
    assert len(set(development)) == len(development)
    assert set(development).isdisjoint(selection)
    assert set(development).isdisjoint(validation)
    assert derive_study_seed("development", 0) == development[0]
    with pytest.raises(ValueError, match="only development"):
        derive_study_seed("confirmatory", 0)


def test_reference_governance_is_four_provisional_simulation_roles() -> None:
    governance = load_reference_governance(ROOT, GOVERNANCE)
    assert tuple(item.authority_id for item in governance.authorities) == (
        "AUTH-01",
        "AUTH-02",
        "AUTH-03",
        "AUTH-04",
    )
    assert all(item.status == "provisional-simulation-role" for item in governance.authorities)
    assert "do not represent legal authority" in governance.limitation


def test_reference_source_requirements_are_honest_before_retrieval() -> None:
    registry = load_reference_source_requirements(ROOT, SOURCES)
    assert len(registry.requirements) == 9
    assert all(item.retrieval_status == "not-retrieved" for item in registry.requirements)
    assert all(item.license_status == "not-assessed" for item in registry.requirements)
    assert registry.runtime_network_access == "forbidden"


def test_reference_source_research_cannot_become_implicit_runtime_data() -> None:
    registry = load_reference_source_research(ROOT, SOURCE_RESEARCH)
    verified = [
        candidate
        for candidate in registry.candidates
        if candidate.research_status == "verified-official-locator"
    ]
    assert {candidate.source_id for candidate in verified} == {
        "REF-SRC-03",
        "REF-SRC-04",
        "REF-SRC-05",
    }
    assert all(candidate.runtime_inclusion == "none" for candidate in registry.candidates)
    assert all(
        candidate.redistribution_status == "not-assessed"
        for candidate in registry.candidates
        if candidate.source_id != "REF-SRC-05"
    )


def test_delivered_small_baseline_verifies_and_tampering_fails(tmp_path: Path) -> None:
    registry = verify_small_baseline(ROOT, BASELINE)
    copied_registry = tmp_path / BASELINE
    copied_registry.parent.mkdir(parents=True)
    shutil.copy2(ROOT / BASELINE, copied_registry)
    for item in registry.files:
        destination = tmp_path / item.relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / item.relative_path, destination)
    verify_small_baseline(tmp_path, BASELINE)
    target = tmp_path / registry.files[0].relative_path
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="digest mismatch"):
        verify_small_baseline(tmp_path, BASELINE)


def test_reference_loader_rejects_symlinked_inputs(tmp_path: Path) -> None:
    source = tmp_path / "source.yaml"
    source.write_bytes((ROOT / CONFIG).read_bytes())
    alias = tmp_path / "alias.yaml"
    alias.symlink_to(source)
    with pytest.raises(ReferenceConfigurationError, match="safe"):
        load_reference_config(tmp_path, Path("alias.yaml"))
