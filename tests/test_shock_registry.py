from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from trace_jepa.workbench.shocks import ShockRegistry, load_shock_registry


REGISTRY_ROOT = Path("configs/shocks/S2")


def test_all_development_registries_are_explicit_empty_r_b_schedules() -> None:
    hashes = set()
    for seed in range(1, 61):
        registry = load_shock_registry(
            f"seed_{seed}.yaml",
            registry_root=REGISTRY_ROOT,
            expected_seed=seed,
            expected_regime="R-B",
        )
        assert registry.entries == ()
        hashes.add(registry.registry_hash)
    assert len(hashes) == 60


def test_registry_hash_is_canonical_and_order_independent_for_mapping_keys() -> None:
    first = ShockRegistry.model_validate(
        {
            "schema_version": "trace-shock-registry-v1",
            "regime": "R-C",
            "seed": 3,
            "entries": [
                {
                    "shock_id": "breach-1",
                    "scheduled_at": 50.0,
                    "shock_type": "levee_breach",
                    "severity": 0.6,
                }
            ],
        }
    )
    second = ShockRegistry.model_validate(
        {
            "entries": [
                {
                    "severity": 0.6,
                    "shock_type": "levee_breach",
                    "scheduled_at": 50.0,
                    "shock_id": "breach-1",
                }
            ],
            "seed": 3,
            "regime": "R-C",
            "schema_version": "trace-shock-registry-v1",
        }
    )
    assert first.registry_hash == second.registry_hash


@pytest.mark.parametrize(
    "entries, message",
    [
        (
            [
                {
                    "shock_id": "same",
                    "scheduled_at": 1,
                    "shock_type": "wind_shift",
                    "severity": 0.2,
                },
                {
                    "shock_id": "same",
                    "scheduled_at": 2,
                    "shock_type": "wind_shift",
                    "severity": 0.2,
                },
            ],
            "unique",
        ),
        (
            [
                {
                    "shock_id": "later",
                    "scheduled_at": 2,
                    "shock_type": "wind_shift",
                    "severity": 0.2,
                },
                {
                    "shock_id": "earlier",
                    "scheduled_at": 1,
                    "shock_type": "wind_shift",
                    "severity": 0.2,
                },
            ],
            "sorted",
        ),
    ],
)
def test_duplicate_and_out_of_order_entries_are_rejected(entries, message) -> None:
    with pytest.raises(ValidationError, match=message):
        ShockRegistry.model_validate(
            {
                "schema_version": "trace-shock-registry-v1",
                "regime": "R-C",
                "seed": 1,
                "entries": entries,
            }
        )


def test_registry_schema_rejects_unknown_fields_and_shock_types() -> None:
    with pytest.raises(ValidationError):
        ShockRegistry.model_validate(
            {
                "schema_version": "trace-shock-registry-v1",
                "regime": "R-C",
                "seed": 1,
                "unexpected": True,
                "entries": [],
            }
        )
    with pytest.raises(ValidationError):
        ShockRegistry.model_validate(
            {
                "schema_version": "trace-shock-registry-v1",
                "regime": "R-C",
                "seed": 1,
                "entries": [
                    {
                        "shock_id": "bad",
                        "scheduled_at": 1,
                        "shock_type": "arbitrary_code_execution",
                        "severity": 1,
                    }
                ],
            }
        )


def test_loader_rejects_path_escape_and_unsafe_yaml(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.yaml"
    outside.write_text(
        "schema_version: trace-shock-registry-v1\nregime: R-B\nseed: 1\nentries: []\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="escapes"):
        load_shock_registry(outside, registry_root=root)

    unsafe = root / "unsafe.yaml"
    unsafe.write_text("!!python/object/apply:os.system ['false']\n", encoding="utf-8")
    with pytest.raises(yaml.YAMLError):
        load_shock_registry(unsafe, registry_root=root)


def test_loader_checks_expected_seed_and_regime() -> None:
    with pytest.raises(ValueError, match="seed"):
        load_shock_registry(
            "seed_1.yaml", registry_root=REGISTRY_ROOT, expected_seed=2
        )
    with pytest.raises(ValueError, match="regime"):
        load_shock_registry(
            "seed_1.yaml", registry_root=REGISTRY_ROOT, expected_regime="R-C"
        )
