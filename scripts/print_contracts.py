from __future__ import annotations

import json

from trace_jepa.contracts import (
    ActionInstance,
    Commitment,
    RealizedOutcome,
    TraceRecord,
    WorldModelEvidence,
)


for model in (
    ActionInstance,
    WorldModelEvidence,
    TraceRecord,
    Commitment,
    RealizedOutcome,
):
    print(f"\n{model.__name__} JSON Schema")
    print(json.dumps(model.model_json_schema(), indent=2))
