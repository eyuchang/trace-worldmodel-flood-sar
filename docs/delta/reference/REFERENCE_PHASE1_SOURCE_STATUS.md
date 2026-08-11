# WF-DFLD-01-REFERENCE Phase 1 source status

Date: 2026-08-11  
Status: source research only; no new runtime data  
Runtime network access: forbidden

## Verified official locators

| ID | Candidate | Current disposition |
|---|---|---|
| `REF-SRC-01` | Sacramento County drainage districts | Official feature-service locator verified, with the State Water Board legal-Delta map retained as an identity cross-check. No Reference snapshot or geometry is approved yet. |
| `REF-SRC-02` | DWR i03 Local Maintenance Areas | Official locator verified. DWR warns that historic boundary accuracy varies; no snapshot or field is approved yet. |
| `REF-SRC-03` | 2025 Census TIGER/Line California places | Official archive locator verified. Administrative place geometry is not an exposure footprint. |
| `REF-SRC-04` | Caltrans State Highway Bridges | Official service locator verified. Crossing identity and graph endpoints remain unbound. |
| `REF-SRC-05` | USGS 3D Hydrography Program | Official service locator verified. A versioned offline snapshot is required. |
| `REF-SRC-06` | DWR Bay-Delta DEM v4.3 | Official catalog and 10 m Delta archive locator verified. The archive has not been downloaded and its raster member, digest, metadata, nodata, and redistribution terms remain unchecked. |
| `REF-SRC-07` | CDEC station metadata | All seven supplied station IDs checked field by field. No threshold is operative. |

Verified means only that the agency and locator identity passed a manual source
check. It does not mean the source is approved, downloaded, redistributed,
scientifically adequate, or bound to the simulator.

Candidate-level terms review currently records the Sacramento County clipped
snapshot as attributable government data, Census and USGS source data as United
States public domain, and the Caltrans inventory as carrying no public-use
restriction. Those dispositions do not authorize a Reference runtime bundle:
every exact query, selected feature, transformation, attribution, and derived
fixture must still be recorded in the later build manifest. DWR, CDEC, facility,
DEM, and OSM redistribution remain unapproved for Reference.

## Material findings

1. The supplied specification calls `MRU` “Middle River at Union Point.” CDEC
   calls it “Middle River at Undine Road.”
2. The supplied specification calls `MSD` “Mokelumne River at Staten.” CDEC
   identifies it as “San Joaquin River at Mossdale Bridge.” A Staten station, if
   required, needs a different verified ID.
3. The Andrus question is not a clean `RD 317` versus `RD 407` conflict.
   Sacramento County distinguishes Lower Andrus (`RD 317`), Andrus (`RD 407`),
   and Upper Andrus (`RD 556`), while the State Water Board's island-level index
   uses Andrus Island (`RD 317`). The Brannan-Andrus maintenance annex also
   associates `RD 317`, `RD 407`, and `RD 2067` with the combined maintenance
   district. The specification's west-levee segment remains unbound until those
   records are spatially reconciled.
4. Caltrans classifies the Threemile Slough Bridge as a movable lift bridge,
   not the fixed bridge stated in the specification.
5. Caltrans identifies Real McCoy II as hydraulically propelled rather than a
   cable ferry. Its official description reserves cable-drawn operation for
   J-Mack.
6. The official Woodward Island project record approves ferry decommissioning
   and replacement-bridge construction, but that approval does not by itself
   establish completion. Current crossing status requires confirmation from San
   Joaquin County, so `XNG-10` remains unbound.
7. Several specified crossings connect to Ryer, Bethel, or Woodward islands,
   which are outside the eight-island Reference extent. They require explicit
   boundary-node semantics rather than invented in-extent endpoints.

## Security and provenance gate before download

For each approved source, the offline builder must:

1. receive a caller-trusted output root and an exact HTTPS URL from a versioned
   registry;
2. reject symlinked roots and unsafe destinations;
3. download to a temporary regular file with a declared byte ceiling;
4. verify response type, size, archive safety, schema, and digest before atomic
   replacement;
5. record retrieval time, URL, response metadata, archive/member digests, CRS,
   datum, license, transformation version, and every selected source feature;
6. keep unredistributable source bytes out of git while retaining locators,
   digests, a reproducible retrieval procedure, and a license-compatible derived
   fixture; and
7. make runtime and CI consume only the frozen offline fixture.

No archive should be downloaded merely because a locator is now known. Source
identity, redistribution, and field fitness must be approved first.

The implemented `trace_reference.geography` inspection seam is deliberately
network-free. It accepts an existing caller-rooted file plus an exact digest,
byte ceiling, media/schema contract, and—where applicable—one exact ZIP member.
It rejects symlinks, traversal, duplicate/encrypted members, excessive expansion,
and digest mismatches, and can write only a deterministic non-operative receipt.
No current research candidate has been promoted through that seam as a runtime
input.

## Remaining source work

- Snapshot and spatially reconcile the Sacramento County Andrus/Brannan district
  polygons with the State Water Board and Brannan-Andrus maintenance records;
  do not assign the specified west-levee segment to a district by island name.
- Select and snapshot the exact DWR levee layers required for geometry versus
  governance; a 2017 anatomy layer cannot be presented as current condition.
- Verify the remaining county crossing identifiers, exact endpoint nodes, road
  ownership, and current operation. Preserve the XNG-03, XNG-08, and XNG-10
  source/specification corrections in the frozen crosswalk.
- Select 3DHP feature classes and snapshot only the Reference waterways.
- Inspect the DEM v4.3 archive and exact raster member after license review.
- Verify current gauge sensor/datum semantics and any threshold source.
- Verify facilities from the responsible agency without inferring staffing or
  availability from a location record.
- Assess OSM only as a separately attributed secondary topology aid where
  authoritative routing fields are unavailable.
