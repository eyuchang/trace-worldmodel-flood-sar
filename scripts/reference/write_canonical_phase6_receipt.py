"""Write a source-bound canonical Phase 6 receipt after the exact container run."""

from __future__ import annotations

import argparse
from pathlib import Path

from trace_reference.validation.canonical_receipt import (
    ReferenceCanonicalReceiptInput,
    write_reference_canonical_phase6_receipt,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--trusted-core-root", type=Path, required=True)
    parser.add_argument("--core-receipt-relative-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--derived-reference-image-digest", required=True)
    parser.add_argument("--docker-engine-version", required=True)
    parser.add_argument("--recorded-utc", required=True)
    arguments = parser.parse_args()
    receipt = write_reference_canonical_phase6_receipt(
        ReferenceCanonicalReceiptInput(
            repository_root=arguments.repository_root,
            trusted_core_root=arguments.trusted_core_root,
            core_receipt_relative_path=arguments.core_receipt_relative_path,
            output_path=arguments.output,
            source_commit=arguments.source_commit,
            derived_reference_image_digest=arguments.derived_reference_image_digest,
            docker_engine_version=arguments.docker_engine_version,
            recorded_utc=arguments.recorded_utc,
        )
    )
    print(receipt.receipt_digest)


if __name__ == "__main__":
    main()
