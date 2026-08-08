"""Compatibility facade for shared bounded artifact I/O."""

from trace_jepa.support.files import (
    ArtifactLocator,
    atomic_write_bytes,
    safe_directory,
    safe_output_file,
    safe_regular_file,
    validate_npz_container,
)

__all__ = [
    "ArtifactLocator",
    "atomic_write_bytes",
    "safe_directory",
    "safe_output_file",
    "safe_regular_file",
    "validate_npz_container",
]
