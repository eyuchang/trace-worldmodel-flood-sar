# WF-DFLD-01-REFERENCE Phase 1 source and topology status

Date: 2026-08-12
Status: offline simulation geography v2 approved for development use; not release-ready
Runtime network access: forbidden

## Completed development package

`delta-reference-geography-v2` binds the 8 islands, 4 communities, and 10
crossings required by the approved Reference extent. It is regenerated from
eight clipped, field-minimized government snapshots under
`data/scenario/delta/reference/geography/sources/`. Every snapshot records its
upstream response digest, exact retrieval endpoint and time, redistribution
disposition, attribution, selected fields, and limitations in
`source_metadata_v2.yaml`. Exact ordered query parameters, upstream-response
digests, feature-selection rules, transformation identifiers, and derived-output
digests are independently bound in `source_retrieval_receipts_v2.yaml`.

Version 1 remains immutable development history. Version 2 corrects source
licensing, identifier semantics, canonical geometry, and fail-closed provenance.
The Sacramento County snapshot is excluded from any release until its
dataset-specific redistribution terms are verified; therefore this package is
not yet release-ready even though it is suitable for local development.

The deterministic builder:

1. validates caller-rooted regular files and exact digests;
2. rejects network access, traversal, and symlinked inputs;
3. validates and, only when necessary, repairs polygon topology while recording
   the repair status, then fixes ring orientation and polygon ordering;
4. stores source geometry in quantized WGS84 microdegrees;
5. performs areas and route distances in NAD83 / UTM zone 10N (`EPSG:26910`);
6. retains both official source identities and simulation-only topology
   semantics; and
7. binds the Python, PyProj, PROJ, Shapely, and GEOS versions used for geometry;
   and
8. regenerates the committed catalog and build manifest byte-for-byte.

The eight island polygons are source-bound operational-maintenance footprints,
not parcel, survey, cadastral, or navigation boundaries. Isleton and Walnut
Grove use Census administrative boundaries only as synthetic-exposure anchors.
Locke and Ryde use GNIS location geometry because no corresponding 2025 Census
place/CDP boundary was returned. Locke's source feature is a multipoint, so its
runtime anchor is explicitly the deterministic centroid of that official
geometry rather than an official point. No real residence, callback data, or
upstream county contact field is present.

## Andrus and Brannan resolution

The source review shows that “Andrus Island” is not a single reclamation
district. Sacramento County separately maps Lower Andrus (`RD 317`), Andrus
(`RD 407`), and Upper Andrus (`RD 556`); DWR also maps Upper Andrus and the
combined Brannan-Andrus Levee Maintenance District. The runtime footprint for
`ISL-01` is therefore the union of the three county polygons, with DWR records
retained as cross-checks for Andrus. `ISL-02` uses the single Sacramento County
`RD 2067` footprint. The combined DWR district is not treated as a Brannan-only
footprint.

Caltrans identifies both State Highway Bridges and Local Bridges as Creative
Commons Attribution datasets. Their catalog records retain attribution. The
County license remains unresolved as described above rather than being inferred
from general government-data availability.

This resolves the island-footprint question without inventing a false choice
between `RD 317` and `RD 407`. It does **not** establish a survey-grade west
levee segment or legal maintenance responsibility for `BREACH-01`. The later
physical model must use an explicitly synthetic, source-anchored breach segment
and preserve that limitation.

## Corrections to the supplied sketch

- Caltrans classifies `XNG-03` (Threemile Slough) as a movable lift bridge, not
  fixed.
- Caltrans classifies Real McCoy II (`XNG-08`) as a hydraulic ferry and J-Mack
  (`XNG-09`) as cable-drawn.
- GNIS verifies the Woodward Island Ferry identity/location, but the reviewed
  official project record does not establish whether replacement construction
  is complete. `XNG-10` therefore remains
  `official-identity-current-type-unresolved`.
- `XNG-06` lies just north of the sketch's provisional exposure bounds and
  `XNG-02`, `XNG-07`, `XNG-08`, `XNG-09`, and `XNG-10` connect exterior places.
  They are boundary connectors in the route graph and do not expand the
  eight-island cohort.
- CDEC identifies `MRU` as Middle River at Undine Road and `MSD` as San Joaquin
  River at Mossdale Bridge. No supplied Reference threshold is operative.

## Topology semantics

Official crossing inventory points anchor ten protocol-declared road crossing
edges. Protocol endpoints express the intended reduced-order access graph; they
are not claims about road ownership or suitability. Seven source-anchor-derived
water links make the eight exposure islands connected for synthetic marine
transfer. Those links carry the explicit label `simulation-topology-only` and
must not be interpreted as channels, navigation routes, or travel-time advice.

## Deferred source fields

The following fields are deliberately excluded from the development geography
until they can be added without overstating source evidence:

- survey-grade levee segment geometry and legal maintenance responsibility;
- field-operational road and water routing;
- the current Woodward crossing type and operability;
- large DEM raster bytes and site-specific hydrodynamic calibration;
- live facility staffing or emergency availability; and
- any current crossing or gauge status.

The reduced-order physical model may use versioned synthetic values for those
fields, but must label them as model parameters rather than official facts.
