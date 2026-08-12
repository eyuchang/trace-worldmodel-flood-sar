# WF-DFLD-01-REFERENCE geography and provenance amendment v2

Date: 2026-08-12  
Status: approved scientific decisions unchanged; corrective development amendment  
Scope: geography, provenance, licensing, and public-delivery lineage only

## Immutable protocol bindings

The reviewed Reference protocol draft remains byte-identical at SHA-256
`03c407ceb1b87041e36f0c58c352840e94bab6cec73a1f69eacd80173e77a552`.
The approved scientific-decision amendment remains bound at SHA-256
`6be6e4a6b4766fb9e66bf7de31924e545503df9202c929587471089076867cca`.
This corrective amendment does not change the approved axes, scenario extent,
physical coefficients, estimands, or validation policy.

## Corrective decisions

1. `delta-reference-geography-v3` supersedes development-only geography v1 and
   v2. The v1/v2 catalogs and the County source snapshot are removed from the
   current tree. Their identifiers and digests remain in this amendment as
   non-redistributed provenance history.
2. The runtime geography uses seven government-source snapshots with established
   redistribution rights. It does not consume Sacramento County bytes.
3. DWR provides a single combined Brannan-Andrus Levee Maintenance District
   (`BALMD`) footprint and a separate Upper Andrus (`RD 556`) footprint. To keep
   two non-overlapping simulation exposure entities without implying survey
   precision, v3 partitions BALMD at the explicitly synthetic longitude
   `-121.623000` degrees. The eastern partition plus DWR Upper Andrus forms the
   Andrus simulation footprint; the western partition forms the Brannan
   simulation footprint. This is a deterministic scenario-design partition,
   not a legal, cadastral, hydrologic, or reclamation-district boundary.
4. Every source feature must have an exact property-key set equal to its receipt's
   `selected_fields`. Extra fields fail before geometry derivation.
5. The geography manifest binds PyProj, PROJ, Shapely, and GEOS exactly. Python
   remains bound by the scenario's digest-pinned execution environment rather
   than being redundantly or ambiguously claimed by the geography manifest.
6. Phase 0 source candidates and provisional statuses are research history.
   `source_lifecycle_erratum_v1.yaml` identifies the authoritative Phase 1 v3
   disposition for each source requirement.

## Public-delivery requirement

The local branch contains prior research commits that included a County snapshot.
Deleting it in a descendant commit does not remove those ancestor Git objects.
No public push may use this local lineage unless Sacramento County supplies
explicit redistribution permission covering those bytes. In the absence of such
permission, delivery must create a sanitized branch from a known-safe base and
apply only reviewed, redistributable changes. A pre-push object/history scan must
prove that the County snapshot digest
`af9c9cb9ea6a79ae569ee156c1e5753df468697fe14cf9a2e3f7f15a97eaaca0`
and its path are absent from every reachable object.

## Scientific consequence

The v3 partition is less granular than the unpublished County-derived development
geometry but has a defensible public provenance boundary. All downstream exposure
and physical claims must retain the `simulation-grade` and `synthetic-partition`
labels. No result may be described as a district-level spatial reconstruction.
