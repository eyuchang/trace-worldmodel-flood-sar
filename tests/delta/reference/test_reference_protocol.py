from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from trace_jepa.support import sha256_file
from trace_reference import (
    REFERENCE_PROTOCOL,
    derive_study_seed,
    load_reference_config,
    load_reference_entity_source_crosswalk,
    load_reference_fault_schedule,
    load_reference_gauge_research,
    load_reference_governance,
    load_reference_source_requirements,
    load_reference_source_research,
    load_reference_topology_design,
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
GAUGE_RESEARCH = Path("data/scenario/delta/reference/sources/gauge_identity_research_v1.yaml")
TOPOLOGY_DESIGN = Path("data/scenario/delta/reference/topology_design_v1.yaml")
ENTITY_CROSSWALK = Path("data/scenario/delta/reference/sources/entity_source_crosswalk_v1.yaml")
FAULT_SCHEDULE = Path(
    "data/scenario/delta/reference_protocol/reference_fault_schedule_v1.json"
)
BASELINE = Path("data/scenario/delta/reference_protocol/small_baseline_v1.json")
PROTOCOL_DRAFT = Path("docs/delta/reference/WF_DFLD_01_REFERENCE_PROTOCOL_DRAFT.md")
GEOGRAPHY_AMENDMENT = Path("docs/delta/reference/WF_DFLD_01_REFERENCE_GEOGRAPHY_AMENDMENT_V2.md")


def test_reference_development_contract_is_explicit_and_nonconfirmatory() -> None:
    config = load_reference_config(ROOT, CONFIG)
    assert config.status == "approved-decisions-development-only"
    assert config.approved_decision_set == "reference-scientific-decisions-v1"
    assert config.protocol_amendment_sha256 == REFERENCE_PROTOCOL.protocol_amendment_sha256
    assert config.geography_amendment_sha256 == REFERENCE_PROTOCOL.geography_amendment_sha256
    assert REFERENCE_PROTOCOL.geography == "delta-reference-geography-v3"
    assert sha256_file(ROOT / PROTOCOL_DRAFT) == config.protocol_document_sha256
    assert sha256_file(ROOT / GEOGRAPHY_AMENDMENT) == config.geography_amendment_sha256
    assert config.timeline.burn_in_start_s == -172_800
    assert config.timeline.evaluation_end_s == 345_600
    assert config.process_targets.breach_time_s == 187_200
    assert config.process_targets.breach_phase_public_report_intensity_per_hour == 95
    assert (
        config.process_targets.breach_phase_start_s,
        config.process_targets.breach_phase_end_s,
    ) == (187_200, 230_400)
    assert config.axes.kappa == 1.0
    assert config.registered_sensitivities[0].value == 0.5
    assert config.registered_sensitivities[0].numerical_gate is False
    assert config.registered_sensitivities[0].status == "registered-design-not-executed"
    assert config.extent.synthetic_people == 1_400
    assert config.generation_order == REFERENCE_GENERATION_ORDER
    assert Path(config.fault_profiles.registered_schedule) == FAULT_SCHEDULE
    assert REFERENCE_PROTOCOL.generation_order == REFERENCE_GENERATION_ORDER
    payload = yaml.safe_load((ROOT / CONFIG).read_text("utf-8"))
    assert "confirmatory" not in payload["study_namespaces"]
    assert "confirmatory_seeds" not in json.dumps(payload).lower()


def test_reference_fault_schedule_covers_required_families_without_runtime_ids() -> None:
    config = load_reference_config(ROOT, CONFIG)
    schedule = load_reference_fault_schedule(
        ROOT,
        Path(config.fault_profiles.registered_schedule),
    )
    assert schedule.profile_id == config.fault_profiles.integration_acceptance
    assert len(schedule.triggers) == 11
    assert all(trigger.anchor_s >= 0 for trigger in schedule.triggers)
    assert all(trigger.fault_id.startswith("reference-fault-") for trigger in schedule.triggers)
    serialized = schedule.model_dump_json()
    assert '"RI-' not in serialized
    assert '"RC-' not in serialized
    assert '"RR-' not in serialized


def test_reference_fault_schedule_fails_closed_on_tamper_and_symlink(tmp_path: Path) -> None:
    payload = json.loads((ROOT / FAULT_SCHEDULE).read_text("utf-8"))
    payload["triggers"][0]["anchor_s"] += 1
    tampered = tmp_path / "faults.json"
    tampered.write_text(json.dumps(payload), "utf-8")
    with pytest.raises(ReferenceConfigurationError, match="digest"):
        load_reference_fault_schedule(tmp_path, Path("faults.json"))

    target = tmp_path / "target.json"
    target.write_bytes((ROOT / FAULT_SCHEDULE).read_bytes())
    alias = tmp_path / "alias.json"
    alias.symlink_to(target)
    with pytest.raises(ReferenceConfigurationError, match="safe"):
        load_reference_fault_schedule(tmp_path, Path("alias.json"))


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
        "REF-SRC-01",
        "REF-SRC-02",
        "REF-SRC-03",
        "REF-SRC-04",
        "REF-SRC-05",
        "REF-SRC-06",
        "REF-SRC-07",
    }
    assert all(candidate.runtime_inclusion == "none" for candidate in registry.candidates)
    redistribution = {
        candidate.source_id: candidate.redistribution_status for candidate in registry.candidates
    }
    assert redistribution["REF-SRC-01"] == ("clipped-government-snapshot-with-attribution")
    assert redistribution["REF-SRC-03"] == "united-states-public-domain"
    assert redistribution["REF-SRC-04"] == "public-use-no-restrictions"
    assert redistribution["REF-SRC-05"] == "united-states-public-domain"
    assert all(
        redistribution[source_id] == "not-assessed"
        for source_id in ("REF-SRC-02", "REF-SRC-06", "REF-SRC-07", "REF-SRC-08", "REF-SRC-09")
    )


def test_reference_gauge_identity_research_corrects_spec_without_thresholds() -> None:
    registry = load_reference_gauge_research(ROOT, GAUGE_RESEARCH)
    identities = {gauge.station_id: gauge for gauge in registry.gauges}
    assert identities["MRU"].official_name == "Middle River at Undine Road"
    assert identities["MSD"].official_name == "San Joaquin River at Mossdale Bridge"
    assert identities["MRU"].identity_status == "corrects-specification"
    assert identities["MSD"].identity_status == "corrects-specification"
    assert all(gauge.threshold_status == "unavailable-non-operative" for gauge in registry.gauges)
    assert all(gauge.runtime_inclusion == "none" for gauge in registry.gauges)


def test_reference_topology_design_is_complete_but_not_runtime_geometry() -> None:
    registry = load_reference_topology_design(ROOT, TOPOLOGY_DESIGN)
    assert len(registry.entities) == 22
    assert tuple(entity.entity_id for entity in registry.entities[:8]) == tuple(
        f"ISL-{index:02d}" for index in range(1, 9)
    )
    assert all(entity.geometry_status == "unbound" for entity in registry.entities)
    assert all(entity.graph_status == "unbound" for entity in registry.entities)
    assert all(entity.runtime_inclusion == "none" for entity in registry.entities)


def test_reference_entity_crosswalk_records_corrections_without_binding_runtime() -> None:
    registry = load_reference_entity_source_crosswalk(ROOT, ENTITY_CROSSWALK)
    requirements = load_reference_source_requirements(ROOT, SOURCES)
    topology = load_reference_topology_design(ROOT, TOPOLOGY_DESIGN)
    entries = {entry.entity_id: entry for entry in registry.entries}
    assert len(entries) == 22
    assert entries["ISL-01"].research_status == (
        "multiple-official-records-require-spatial-crosswalk"
    )
    assert entries["ISL-01"].official_identifiers == (
        "RD 317 Lower Andrus Island",
        "RD 407 Andrus Island",
        "RD 556 Upper Andrus Island",
    )
    assert entries["XNG-03"].research_status == "official-record-corrects-design"
    assert "movable lift" in entries["XNG-03"].official_identifiers
    assert entries["XNG-08"].research_status == "official-record-corrects-design"
    assert entries["XNG-10"].research_status == ("official-record-raises-current-status-question")
    requirement_ids = {item.source_id for item in requirements.requirements}
    assert all(set(entry.source_requirement_ids) <= requirement_ids for entry in registry.entries)
    assert tuple(entry.design_name for entry in registry.entries) == tuple(
        entity.design_name for entity in topology.entities
    )
    assert all(entry.binding_status == "unbound" for entry in registry.entries)
    assert all(entry.runtime_inclusion == "none" for entry in registry.entries)


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
