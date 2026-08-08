"""TRACE flow and reconciliation-evaluation publication figures."""

from __future__ import annotations

from typing import Any

from .primitives import COLORS, svg_document, text


def trace_flow_figure(summary: Any, trace_records: Any, reconciliation: Any | None = None) -> bytes:
    body: list[str] = []
    nodes = [
        (40, "Hidden causal truth", f"{summary['latent_incidents']} latent incidents", "#d5f5e3"),
        (225, "Lossy evidence", f"{summary['observed_calls']} visible reports", "#d6eaf8"),
        (
            410,
            "Controller beliefs",
            f"{summary['visible_evidence_repairs']} visible repairs",
            "#fcf3cf",
        ),
        (595, "TRACE governance", f"{len(trace_records)} record versions", "#e8daef"),
        (
            780,
            "Durable outcomes",
            f"{summary['allocations']} allocate · {summary['refusals']} refuse",
            "#fadbd8",
        ),
    ]
    for x, title, subtitle, color in nodes:
        body.append(
            f'<rect x="{x}" y="220" width="145" height="120" rx="10" fill="{color}" stroke="#566573"/>'
        )
        body.append(text(x + 12, 255, title, size=13, weight=700))
        body.append(text(x + 12, 283, subtitle, size=11))
        if x < 780:
            body.append(
                f'<line x1="{x + 145}" y1="280" x2="{x + 180}" y2="280" stroke="#566573" stroke-width="2"/>'
            )
            body.append(
                f'<polygon points="{x + 180},280 {x + 170},274 {x + 170},286" fill="#566573"/>'
            )
    body.append(
        text(
            45,
            395,
            "Truth IDs and person IDs never cross the hidden/public boundary.",
            size=13,
            weight=700,
        )
    )
    body.append(
        text(
            45,
            425,
            (
                "Confirmed merges use hard evidence or conservative multi-family visible evidence."
                if reconciliation is not None
                else (
                    "Repairs use shared callback tokens, report revisions, and "
                    "spatial/temporal similarity."
                )
            ),
            size=12,
        )
    )
    body.append(
        text(
            45,
            455,
            "Every allocation cites the exact consumed TRACE record version that authorized it.",
            size=12,
        )
    )
    body.append(
        text(
            45,
            485,
            "Toy is a transparent teaching fixture; MLP and V-JEPA remain unqualified by default.",
            size=12,
        )
    )
    if reconciliation is not None:
        suspected = sum(item["status"] == "suspected" for item in reconciliation["links"])
        body.append(
            text(
                45,
                515,
                f"Ambiguous links remain reversible and separate: {suspected} suspected links.",
                size=12,
            )
        )
    return svg_document("Ground truth → lossy evidence → beliefs → TRACE decisions", body)


def reconciliation_figure(summary: Any) -> bytes:
    reconciliation = summary["reconciliation"]
    metrics = (
        ("pairwise_precision", "Pairwise precision", COLORS["capacity"]),
        ("pairwise_recall", "Pairwise recall", COLORS["accent"]),
        ("pairwise_f1", "Pairwise F1", COLORS["water"]),
        ("false_merge_rate", "False-merge rate", COLORS["hazard"]),
    )
    body = [
        text(60, 82, "Descriptive book-seed partition metrics", size=13, weight=700),
        text(555, 82, "Holdout comparison is reported separately", size=10),
    ]
    for index, (key, label, color) in enumerate(metrics):
        value = float(reconciliation[key])
        y = 145 + index * 95
        body.append(f'<rect x="250" y="{y - 20}" width="600" height="30" fill="#edf2f4"/>')
        body.append(
            f'<rect x="250" y="{y - 20}" width="{600 * value:.1f}" height="30" fill="{color}"/>'
        )
        body.append(text(60, y, label, size=12, weight=700))
        body.append(text(865, y, f"{value:.3f}", size=12, weight=700))
    body.append(
        text(
            60,
            560,
            "These scores use hidden lineage only after runtime; the controller never receives it.",
            size=11,
        )
    )
    return svg_document("Controller reconciliation evaluation", body)
