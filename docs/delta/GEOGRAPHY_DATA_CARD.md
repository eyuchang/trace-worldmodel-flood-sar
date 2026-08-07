# Delta Small geography data card

## Intended use

This bundle supplies simulation-grade operational anchors for
WF-DFLD-01-SMALL. It is not suitable for navigation, surveying, levee
engineering, parcel analysis, dispatch, or public-safety operations.

Runtime input:
`data/scenario/delta/geography/delta_small_geography_v3.yaml`.
Build provenance:
`data/scenario/delta/geography/build_manifest_v3.json`.

Source geometry is retained in WGS84. Metric operations use NAD83 / UTM Zone
10N (`EPSG:26910`). Runtime coordinates are quantized integer millimetres and
also carry WGS84 integer degrees at `1e-7` resolution. Quantization supports
deterministic computation; it does not imply millimetre measurement accuracy.

## Source hierarchy

| Use | Primary source | Cross-check / limitation |
|---|---|---|
| Andrus/Brannan footprint and governance | Sacramento County drainage/reclamation district GIS | DWR Local Maintenance Area metadata; mapping boundaries are not surveys |
| Isleton administrative boundary | 2025 Census TIGER/Line place geometry | Administrative, not exposure or parcel boundary |
| XNG-03/XNG-04 | Caltrans State Highway Bridges inventory | Inventory coordinates/design, not live bridge status |
| Waterways | USGS NHD flowlines | General hydrography, simplified by 10 m tolerance |
| Elevation summary | DWR Bay-Delta DEM v4.3, Delta 10 m raster | NAVD88 summaries only; no navigation or levee design use |
| Gauges | CDEC station metadata | RVB alone has reviewed thresholds; MRU/FPT are observational |
| Fire base | City of Isleton official address and apparatus record | OSM Nominatim is a secondary address geocode |
| Boat launch | State Parks unit boundary and DBW directory | No reviewed ramp coordinate; park centroid is non-operative |

Each `SourceRecord` stores source ID/title, a human landing page separately from
any machine-readable retrieval endpoint, retrieval time,
source tier, use, status, license locator, redistribution decision, SHA-256, and
byte length. The DEM has separate records for the 69,839,544-byte upstream ZIP
and the exact 504,815,460-byte extracted GeoTIFF, including archive member,
extraction command, CRS, vertical datum, and nodata handling.

The full City of Isleton and DBW HTML pages are not redistributed. Project-owned
factual extracts retain their upstream URL, retrieval time, and upstream digest.
The DWR raster/archive are also not committed; only their digests, retrieval
procedure, provenance, and derived island summaries are distributed.

## Geometry QA

Automated checks require:

- valid, positive-area island polygons;
- no unrecorded geometry repair;
- source/scenario area values retained separately;
- deterministic structures contained by the declared footprint;
- Isleton structures contained by both Census Isleton and county Andrus;
- Brannan structures contained by the county Brannan footprint;
- crossing points within 150 m of a retained waterway line;
- UTM/WGS84 coordinate reconstruction within fixed quantization tolerance;
- complete governance coverage for both islands;
- a routing-operative fire base and non-operative approximate launch;
- no obsolete v1 runtime catalog.

The source-derived and scenario-stated acre/elevation values are both retained.
Differences reflect boundary definitions, raster resolution/datum, and the fact
that specification values are scenario parameters. One is never silently
substituted for the other.

## Gauge registry

- `RVB`: Sacramento River at Rio Vista Bridge; action/minor-flood thresholds
  available in the reviewed CDEC record and permitted for threshold logic.
- `MRU`: Middle River at Undine Road; no reviewed operative thresholds.
- `FPT`: Sacramento River at Freeport; no reviewed operative thresholds.

Unavailable thresholds are encoded as unavailable/non-operative, not zero and
not copied from another station.

## Offline build

Normal runtime and CI perform no network requests. A maintainer with the exact
DWR archive and extracted raster can rebuild:

```bash
.venv/bin/python scripts/build_delta_small_geography.py \
  --source-root data/scenario/delta/geography/sources \
  --geography-output data/scenario/delta/geography/delta_small_geography_v3.yaml \
  --manifest-output data/scenario/delta/geography/build_manifest_v3.json \
  --dem-archive /path/to/dem_delta_10m_20250312.zip \
  --dem-raster /path/to/dem_delta_10m_20250312.tif
```

`--refresh-sources` is an explicit maintainer action and is never used by run,
replay, validation, publication, or CI.

Refresh downloads to a temporary regular file, validates size, media type,
schema, digest, archive members, and traversal safety, then replaces a snapshot
atomically. A source without a machine-readable endpoint fails safely rather
than saving an HTML landing page as JSON. Output symlinks and parents resolving
outside the requested root are rejected.
