"""Shared immutable model base for the Delta Small domain."""

from pydantic import BaseModel, ConfigDict


class DeltaModel(BaseModel):
    """Reject unknown fields and prevent attribute reassignment after validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)
