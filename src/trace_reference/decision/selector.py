"""Frozen deterministic base selector over an unchanged response-bundle catalog."""

from __future__ import annotations

from trace_jepa.contracts import CommitmentDecision

from .canonical import decision_digest, verify_model_digest
from .domain import (
    BaseSelectionReceipt,
    BaseSelectionRequest,
    ResponseBundleCatalog,
    ResponseBundleKind,
)


class BaseReferenceSelector:
    """Simple declared-value selector with no branching, screening, or search."""

    selector_id = "reference-base-selector-v1"

    def select(
        self,
        request: BaseSelectionRequest,
        catalog: ResponseBundleCatalog,
    ) -> BaseSelectionReceipt:
        if request.catalog_digest != catalog.catalog_digest:
            raise ValueError("Reference selector request does not bind its catalog")
        if not verify_model_digest(catalog, digest_field="catalog_digest"):
            raise ValueError("Reference response-bundle catalog digest is invalid")
        if any(
            not verify_model_digest(item, digest_field="bundle_digest") for item in catalog.bundles
        ):
            raise ValueError("Reference response-bundle digest is invalid")
        fallback: CommitmentDecision | None
        if not catalog.complete_for_declared_grammar:
            selected = None
            fallback = CommitmentDecision.HOLD
            values: tuple[tuple[str, int], ...] = ()
            reason = "Proposal grammar was incomplete or unsupported; selection failed closed."
        else:
            kind_value = {
                ResponseBundleKind.ACT_NOW: 300,
                ResponseBundleKind.SAFE_ALTERNATIVE: 200,
                ResponseBundleKind.ACQUIRE_THEN_REASSESS: 100,
            }
            values = tuple(
                sorted(
                    ((item.bundle_id, kind_value[item.kind]) for item in catalog.bundles),
                    key=lambda item: item[0],
                )
            )
            selected = (
                min(
                    catalog.bundles,
                    key=lambda item: (-kind_value[item.kind], item.bundle_id),
                ).bundle_id
                if catalog.bundles
                else None
            )
            fallback = None if selected is not None else CommitmentDecision.HOLD
            reason = (
                "Selected by frozen kind value with canonical bundle-ID tie break."
                if selected is not None
                else "No TRACE-eligible response bundle was available."
            )
        body = {
            "schema_version": "delta-reference-base-selection-v1",
            "selector_id": self.selector_id,
            "catalog_digest": catalog.catalog_digest,
            "public_snapshot_digest": request.public_snapshot_digest,
            "trace_prefix_digest": request.trace_prefix_digest,
            "selected_bundle_id": selected,
            "fallback_disposition": fallback.value if fallback is not None else None,
            "ordered_values": values,
            "tie_rule": "highest-fixed-base-value-then-canonical-bundle-id",
            "simulated_compute_latency_s": 1,
            "reason": reason,
        }
        return BaseSelectionReceipt(**body, selection_digest=decision_digest(body))
