#!/usr/bin/env python
"""Register the RQ5 protocol before any held-out campaign run."""

from __future__ import annotations

import argparse
from pathlib import Path

from trace_jepa.experimental import ProtocolRegistry, load_rq5_protocol


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Register RQ5 under the campaign freeze discipline."
    )
    parser.add_argument(
        "--protocol",
        type=Path,
        default=Path("configs/protocols/rq5_revalidation_guard.yaml"),
    )
    parser.add_argument(
        "--store",
        type=Path,
        default=Path("artifacts/protocols"),
    )
    args = parser.parse_args()
    protocol = load_rq5_protocol(args.protocol)
    registry = ProtocolRegistry(store_path=args.store)
    digest = registry.register(protocol)
    print(f"Registered {protocol.protocol_id}")
    print(f"Content hash: {digest}")
    print(f"Store: {args.store / (protocol.protocol_id + '.json')}")
    print(f"Scenarios: {[s.scenario_id for s in protocol.scenarios]}")
    print(f"Arms: {[a.arm_id for a in protocol.arms]}")
    print(f"Invariant: {protocol.invariant.invariant_id}")


if __name__ == "__main__":
    main()
