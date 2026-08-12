# WF-DFLD-01-REFERENCE protocol amendment v3

## Document control

| Field | Value |
|---|---|
| Amendment ID | `reference-protocol-amendment-v3` |
| Decision set | `reference-scientific-decisions-v3` |
| Status | Approved-scope feasibility correction; development only |
| Date | 2026-08-12 |
| Corrects | Taxonomy table in `reference-protocol-amendment-v2` |
| Amendment v2 SHA-256 | `7065bc5930ec2f8ecf550198e92fab0cf0258685d237c9c57153ef0ba1965650` |
| Confirmatory authorization | None |
| LEAP authorization | None |

Amendment v2 correctly freezes the approved 1,800--2,200 synthetic latent-
incident band, its 2,000-incident fitting midpoint, the truth-first fitting
sequence, and its nonempirical interpretation. Its provisional 7% target for
`levee_inspection`, however, is infeasible under the already approved physical
model: Reference contains one explicitly modeled levee segment, and continuous
episode formation exposes approximately five distinct evaluation episodes per
development world. A 7% target would require inventing unsourced segments or
violating the one-incident-per-continuous-episode rule.

The adverse feasibility result is retained in amendment v2 and the calibration
audit. No coefficient was fit before this correction.

## Corrected synthetic composition

The following table supersedes only the composition table in amendment v2:

| Latent incident type | Target share |
|---|---:|
| `information_need` | 39% |
| `hazard_response` | 30% |
| `welfare_check` | 21% |
| `levee_inspection` | 0.2% |
| `animal_rescue` | 3% |
| `missing_person` | 1.8% |
| `stranded_structure` | 2% |
| `vehicle_rescue` | 1.5% |
| `medical_access` | 1.5% |

Information, hazard/access, and welfare episodes comprise 90% of the design.
Direct human rescue/medical episodes (`stranded_structure`, `vehicle_rescue`,
and `medical_access`) remain 5%. At the 2,000-incident fitting midpoint, the
levee target is four incidents, consistent with the modeled segment's episode
support without forcing a per-seed count.

These remain synthetic mechanism-design weights rather than empirical frequency
estimates. The fit must preserve stochastic per-seed totals, show type-specific
residuals, and report any type whose available episode support prevents the
target from being attained. It must not create new infrastructure, alter
physical state, or collapse distinct episode types to improve the objective.

All other requirements and stop boundaries in amendments v1 and v2 remain in
force.
