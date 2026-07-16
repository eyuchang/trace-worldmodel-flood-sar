# D0.2 Step 3 Release Notes

## Added

- MapLibre real-map background with 55-degree pitch.
- Live GeoJSON operational sources for flood, routes, paths, hazards, incidents,
  assets, and locations.
- Controller, truth, and difference overlay semantics.
- Click selection for routes, assets, incidents, hazards, and locations.
- Smooth short interpolation for asset positions between snapshots.
- Inline favicon, removing the previous harmless `/favicon.ico` 404.
- Null-safe MapLibre style expressions using `coalesce`.
- Three static contract tests and a Step-3 verifier.

## Preserved

- Graph-constrained simulator navigation.
- Append-only TRACE and event repositories.
- Mission Controller versus simulation-truth separation.
- Existing S1-S5 reasoning controls.
- Hidden SVG renderer as a fallback only while the map initializes.

## Not yet claimed

- The synthetic overlay follows real-world waterway geometry.
- The background map influences planning.
- Elevation terrain is enabled.
- Map-click geocoding is implemented.
- The simple point symbols are final production asset models.
