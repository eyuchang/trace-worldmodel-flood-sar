# WF-DFLD-01-SMALL v2 protocol amendment

Status: frozen before confirmatory-v5 execution.

The v5 audit found a conflict between the prose scope (local-tier resources only) and the frozen `kappa=0.5` capacity table (local plus county). With exact capability-aware matching, the local one-engine/one-boat inventory produced a peak ratio of 3.0 rather than the intended approximately 1.5. That result remains adverse audit evidence; it is not overwritten or relabeled.

The v2 scenario resolves the contract conflict by adding a fixed, preauthorized Rio Vista automatic-aid engine and rescue boat at T+5,400 seconds. Official City materials document Station 55, Type I engines, a Zodiac rescue boat, water-rescue capability, and automatic aid to Isleton. The selected pair and its arrival time are frozen teaching assumptions, not claims about actual staffing, response time, or operational readiness. The simulator generates no request, negotiation, authority transfer, mutual-aid tier, or federation event.

The former ratio also mixed active committed work in its numerator with only free resources in its denominator. v2 separates two quantities:

- `gross-compatible-scenario-load-v2` is active truth demand divided by scheduled, mobilized, reachable, capability-compatible gross capacity. It is calculated independently of policy and predictor behavior and is the metric associated with the approximately 1.5 requirement.
- `residual-operational-pressure-v2` subtracts demand covered by active authorized commitments and divides the remainder by free compatible capacity. It is a controller-dependent diagnostic, not the headline scenario difficulty.

The amendment changes resource availability and metrics only. Generator v6 reuses the v5 random namespace. For every fixed seed, geography, meteorology, hydrology, crossing state, cohort, latent incidents, public calls, hidden lineage, and prior profile must remain byte-identical.

## Preserved v5 evidence

- Source commit: `f6d755982fcc727b98f1a6b73e98f1e4a970b0f6`
- Archived configuration SHA-256: `a97cb37c0547183828019ca5bc56662af9d3cc73db5eebc906f8e3f11975939b`
- Book-v1 manifest SHA-256: `ad69d57fde24db6c7c49080c71398bdbec59f7f164e42470c62e94c1e6581e19`
- v5 validation report SHA-256: `d51e17364c254032a8118a9de633425c82f9689c7a523582a5706e40238b817b`
- Book result: 45 calls, 7 allocations, 28 refusals, 10 visible-evidence repairs, peak hybrid ratio 3.0.

The complete immutable file inventory is the manifest inside `data/scenario/delta/reference/wf_dfld_01_small_book_v1`.
