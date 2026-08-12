"""Create bounded, field-minimized Reference source snapshots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from trace_jepa.support import ArtifactLocator, atomic_write_bytes, canonical_json_bytes


def _bounded_feature_collection(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 25_000_000:
        raise ValueError("snapshot input must be a bounded regular file")
    try:
        value = json.loads(path.read_text("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("snapshot input is not valid UTF-8 GeoJSON") from exc
    if not isinstance(value, dict) or value.get("type") != "FeatureCollection":
        raise ValueError("snapshot input must be a GeoJSON FeatureCollection")
    if not isinstance(value.get("features"), list):
        raise TypeError("snapshot input must contain a feature array")
    return value


def write_minimized_snapshot(
    *,
    input_path: Path,
    output_root: Path,
    relative_name: Path,
    allowed_fields: tuple[str, ...],
    object_ids: tuple[int, ...] | None = None,
) -> None:
    """Write canonical source geometry with only declared non-personal fields."""

    payload = _bounded_feature_collection(input_path)
    allowed = set(allowed_fields)
    selected: list[dict[str, Any]] = []
    for item in payload["features"]:
        if not isinstance(item, dict) or not isinstance(item.get("properties"), dict):
            raise TypeError("snapshot feature must contain property and geometry objects")
        properties = item["properties"]
        if object_ids is not None and int(properties.get("OBJECTID", -1)) not in object_ids:
            continue
        selected.append(
            {
                "type": "Feature",
                "properties": {key: properties.get(key) for key in sorted(allowed)},
                "geometry": item.get("geometry"),
            }
        )
    if object_ids is not None:
        observed = {int(item["properties"]["OBJECTID"]) for item in selected}
        if observed != set(object_ids):
            raise ValueError("snapshot did not contain every requested OBJECTID")
    minimized = {"type": "FeatureCollection", "features": selected}
    atomic_write_bytes(
        output_root / relative_name,
        canonical_json_bytes(minimized),
        root=output_root,
        label="Reference minimized source snapshot",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fields", required=True)
    parser.add_argument("--object-ids", default="")
    args = parser.parse_args()
    input_path = ArtifactLocator(
        root=args.input_root,
        relative_name=args.input,
        maximum_bytes=25_000_000,
        label="Reference snapshot input",
    ).resolve()
    object_ids = tuple(int(item) for item in args.object_ids.split(",") if item)
    write_minimized_snapshot(
        input_path=input_path,
        output_root=args.output_root,
        relative_name=args.output,
        allowed_fields=tuple(item for item in args.fields.split(",") if item),
        object_ids=object_ids or None,
    )


if __name__ == "__main__":
    main()
