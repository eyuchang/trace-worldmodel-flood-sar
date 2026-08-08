"""Deterministic publication-bundle orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trace_jepa.scenario.delta.provenance.artifacts import (
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    verify_scenario_artifacts,
)
from trace_jepa.support import atomic_write_bytes

from .load_figures import (
    gross_load_figure,
    metric_sensitivity_figure,
    residual_pressure_figure,
    strict_load_figure,
    strict_residual_pressure_figure,
)
from .primitives import load_json
from .timeline import timeline_figure
from .topology import topology_figure
from .trace_figures import reconciliation_figure, trace_flow_figure


@dataclass(frozen=True)
class ReferenceData:
    geography: Any
    resources: Any
    resource_provenance: Any
    meteorology: Any
    hydrology: Any
    calls: Any
    ground_truth: Any
    windows: Any
    summary: Any
    validation: Any
    trace_records: Any
    coordination: Any | None
    reconciliation: Any | None

    @property
    def is_modern(self) -> bool:
        return bool(self.windows and "strict_concurrent_load_ratio_milli" in self.windows[0])

    @property
    def is_v8(self) -> bool:
        return self.summary.get("schema_version") in {
            "delta-small-machine-result-summary-v4",
            "delta-small-machine-result-summary-v5",
        }


def _optional_json(root: Path, name: str, *, enabled: bool) -> Any | None:
    path = root / name
    return load_json(path) if enabled and path.is_file() else None


def _load_reference(root: Path) -> ReferenceData:
    summary = load_json(root / "result_summary.json")
    is_v8 = summary.get("schema_version") in {
        "delta-small-machine-result-summary-v4",
        "delta-small-machine-result-summary-v5",
    }
    return ReferenceData(
        geography=load_json(root / "geography.json"),
        resources=load_json(root / "resources.json"),
        resource_provenance=load_json(root / "resource_provenance.json"),
        meteorology=load_json(root / "meteorology.json"),
        hydrology=load_json(root / "hydrology.json"),
        calls=load_json(root / "calls.json"),
        ground_truth=load_json(root / "ground_truth.json"),
        windows=load_json(root / "demand_capacity.json"),
        summary=summary,
        validation=load_json(root / "validation_summary.json"),
        trace_records=load_json(root / "trace_records.json"),
        coordination=_optional_json(root, "coordination.json", enabled=is_v8),
        reconciliation=_optional_json(root, "controller_reconciliation.json", enabled=is_v8),
    )


def _figure_payloads(data: ReferenceData) -> dict[str, bytes]:
    figures = {
        "delta_small_topology.svg": topology_figure(
            data.geography, data.resources, data.resource_provenance
        ),
        "delta_small_timeline.svg": timeline_figure(
            data.meteorology,
            data.hydrology,
            data.calls,
            data.resources,
            data.ground_truth if data.is_v8 else None,
            data.coordination,
        ),
        "delta_small_trace_walkthrough.svg": trace_flow_figure(
            data.summary, data.trace_records, data.reconciliation
        ),
    }
    if data.is_v8:
        figures["delta_small_reconciliation.svg"] = reconciliation_figure(data.summary)
    if data.is_modern:
        figures.update(
            {
                "delta_small_strict_load.svg": strict_load_figure(data.windows),
                "delta_small_strict_residual_pressure.svg": strict_residual_pressure_figure(
                    data.windows
                ),
                "delta_small_metric_sensitivity.svg": metric_sensitivity_figure(data.windows),
            }
        )
    else:
        figures.update(
            {
                "delta_small_gross_load.svg": gross_load_figure(data.windows),
                "delta_small_residual_pressure.svg": residual_pressure_figure(data.windows),
            }
        )
    return figures


def _result_table(data: ReferenceData) -> bytes:
    schema = (
        "delta-small-publication-result-table-v5"
        if data.is_v8
        else (
            "delta-small-publication-result-table-v4"
            if data.is_modern
            else "delta-small-publication-result-table-v3"
        )
    )
    return canonical_json_bytes(
        {
            "schema_version": schema,
            "book_walkthrough": data.summary,
            "registered_validation": data.validation,
        }
    )


def _bundle_schema(data: ReferenceData) -> str:
    if data.is_v8:
        return "delta-small-publication-bundle-v4"
    return (
        "delta-small-publication-bundle-v3"
        if data.is_modern
        else "delta-small-publication-bundle-v2"
    )


def _write_payload(output_root: Path, file_name: str, payload: bytes) -> dict[str, object]:
    atomic_write_bytes(
        output_root / file_name,
        payload,
        root=output_root,
        label=f"publication artifact {file_name}",
    )
    return {"file_name": file_name, "sha256": sha256_bytes(payload), "byte_length": len(payload)}


def publish_reference_bundle(reference_root: Path, output_root: Path) -> dict[str, object]:
    """Verify a reference bundle and deterministically publish all paper figures."""

    verify_scenario_artifacts(reference_root)
    if output_root.is_symlink() or output_root.parent.is_symlink():
        raise ValueError("publication output root and parent must not be symlinks")
    output_root.mkdir(parents=True, exist_ok=True)
    data = _load_reference(reference_root)
    descriptors = [
        _write_payload(output_root, file_name, payload)
        for file_name, payload in sorted(_figure_payloads(data).items())
    ]
    result_table = _result_table(data)
    descriptors.append(_write_payload(output_root, "publication_result_table.json", result_table))
    manifest: dict[str, object] = {
        "schema_version": _bundle_schema(data),
        "reference_manifest_sha256": sha256_file(reference_root / "manifest.json"),
        "metadata_policy": "deterministic-svg-no-timestamps-no-notebook",
        "artifacts": descriptors,
    }
    atomic_write_bytes(
        output_root / "publication_manifest.json",
        canonical_json_bytes(manifest),
        root=output_root,
        label="publication manifest",
    )
    return manifest
