"""Build the Reference geography from committed offline sources."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, cast

import yaml

from trace_jepa.support import ArtifactLocator

from .builder import build_reference_geography


def _source_metadata(path: Path) -> list[dict[str, Any]]:
    try:
        value = yaml.safe_load(path.read_text("utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError("Reference source metadata is not valid bounded YAML") from exc
    if not isinstance(value, dict) or not isinstance(value.get("sources"), list):
        raise TypeError("Reference source metadata requires a source list")
    return cast(list[dict[str, Any]], value["sources"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    metadata_path = ArtifactLocator(
        root=args.input_root,
        relative_name=args.metadata,
        maximum_bytes=1_000_000,
        label="Reference geography source metadata",
    ).resolve()
    build_reference_geography(
        source_root=args.input_root / "sources",
        source_metadata=_source_metadata(metadata_path),
        output_root=args.output_root,
    )


if __name__ == "__main__":
    main()
