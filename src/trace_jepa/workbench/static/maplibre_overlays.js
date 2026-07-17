/*
 * TRACE-WorldModel Flood-SAR: MapLibre operational overlays.
 *
 * This module is intentionally framework-free. It converts the existing
 * local simulation coordinates into a display-only geographic reference,
 * builds GeoJSON feature collections from each WebSocket snapshot, and keeps
 * all operational layers synchronized with the simulator.
 *
 * IMPORTANT: this adapter does not influence planning. The simulator's
 * PathSegment edge sequence remains authoritative. The map only renders that
 * sequence.
 */
(() => {
  "use strict";

  const EMPTY_COLLECTION = Object.freeze({
    type: "FeatureCollection",
    features: [],
  });

  const DISPLAY_REFERENCE = Object.freeze({
    version: "synthetic-display-georef-v1",
    origin: Object.freeze({ lon: -121.6200, lat: 38.0400 }),
    metersPerUnit: 24.0,
    localBounds: Object.freeze({ xMin: 0, yMin: 0, xMax: 100, yMax: 80 }),
    pitch: 55,
    bearing: -18,
    maxPitch: 75,
    styleUrl: "https://tiles.openfreemap.org/styles/liberty",
  });

  const SOURCE_IDS = Object.freeze({
    flood: "trace-flood",
    routes: "trace-routes",
    routeLabels: "trace-route-labels",
    authorizedPaths: "trace-authorized-paths",
    hazards: "trace-hazards",
    incidents: "trace-incidents",
    assets: "trace-assets",
    locations: "trace-locations",
  });

  const FLOOD_POLYGON_LOCAL = Object.freeze([
    [0, 24],
    [18, 22],
    [36, 31],
    [52, 28],
    [72, 38],
    [100, 32],
    [100, 80],
    [0, 80],
    [0, 24],
  ]);

  let map = null;
  let ready = false;
  let fitted = false;
  let selectObject = () => {};
  let assetAnimationFrame = null;
  let previousAssetFeatures = new Map();

  function asPosition(value) {
    if (Array.isArray(value)) {
      return { x: Number(value[0]), y: Number(value[1]) };
    }
    return {
      x: Number(value?.x ?? 0),
      y: Number(value?.y ?? 0),
    };
  }

  function localToLngLat(value) {
    const position = asPosition(value);
    const metersEast = position.x * DISPLAY_REFERENCE.metersPerUnit;
    const metersNorth = position.y * DISPLAY_REFERENCE.metersPerUnit;
    const latRadians = DISPLAY_REFERENCE.origin.lat * Math.PI / 180;
    const metersPerDegreeLat = 111_320;
    const metersPerDegreeLon = Math.max(1, metersPerDegreeLat * Math.cos(latRadians));

    return [
      DISPLAY_REFERENCE.origin.lon + metersEast / metersPerDegreeLon,
      DISPLAY_REFERENCE.origin.lat + metersNorth / metersPerDegreeLat,
    ];
  }

  function feature(geometry, properties = {}, id = undefined) {
    const result = {
      type: "Feature",
      geometry,
      properties,
    };
    if (id !== undefined) result.id = id;
    return result;
  }

  function collection(features) {
    return {
      type: "FeatureCollection",
      features,
    };
  }

  function addSource(id) {
    if (!map.getSource(id)) {
      map.addSource(id, {
        type: "geojson",
        data: EMPTY_COLLECTION,
        promoteId: "feature_id",
      });
    }
  }

  function setSourceData(id, data) {
    const source = map?.getSource(id);
    if (source && typeof source.setData === "function") {
      source.setData(data);
    }
  }

  function routeVisualStatus(routeId, snapshot, view) {
    const truth = snapshot.truth.routes[routeId];
    const belief = snapshot.controller.route_beliefs[routeId];
    const truthStatus = truth.open ? "open" : "blocked";
    const beliefStatus = belief?.status || "unknown";

    if (view === "truth") {
      return { status: truthStatus, label: truthStatus };
    }
    if (view === "controller") {
      return { status: beliefStatus, label: beliefStatus };
    }

    const mismatch = beliefStatus === "unknown" || beliefStatus !== truthStatus;
    return {
      status: mismatch ? "mismatch" : truthStatus,
      label: `${beliefStatus} / ${truthStatus}`,
    };
  }

  function edgeVisualStatus(routeId, edgeIndex, snapshot, view) {
    const route = snapshot.truth.routes[routeId];
    const belief = snapshot.controller.route_beliefs[routeId];
    const truthStatus = route.edge_open?.[edgeIndex] === false ? "blocked" : "open";

    let beliefStatus = belief?.status || "unknown";
    if (beliefStatus === "blocked") {
      beliefStatus = Number(belief?.blocked_segment_index) === edgeIndex ? "blocked" : "unknown";
    }

    if (view === "truth") return truthStatus;
    if (view === "controller") return beliefStatus;
    return beliefStatus === "unknown" || beliefStatus !== truthStatus
      ? "mismatch"
      : truthStatus;
  }

  function routeFeatures(snapshot, view) {
    const features = [];
    Object.entries(snapshot.truth.routes).forEach(([routeId, route]) => {
      const visual = routeVisualStatus(routeId, snapshot, view);
      const waypoints = route.waypoints || [];
      for (let index = 0; index < waypoints.length - 1; index += 1) {
        const status = edgeVisualStatus(routeId, index, snapshot, view);
        features.push(feature(
          {
            type: "LineString",
            coordinates: [
              localToLngLat(waypoints[index]),
              localToLngLat(waypoints[index + 1]),
            ],
          },
          {
            feature_id: `route:${routeId}:edge:${index}`,
            object_type: "route",
            object_id: routeId,
            route_id: routeId,
            route_label: String(route.label || routeId),
            edge_index: index,
            status,
            route_status: visual.status,
            route_status_label: visual.label,
            mode: String(route.mode || "water"),
            water_depth: Number(route.water_depth ?? 0),
            open_truth: route.edge_open?.[index] !== false,
          },
          `route:${routeId}:edge:${index}`,
        ));
      }
    });
    return collection(features);
  }

  function routeLabelFeatures(snapshot, view) {
    const features = [];
    Object.entries(snapshot.truth.routes).forEach(([routeId, route]) => {
      const waypoints = route.waypoints || [];
      if (waypoints.length === 0) return;
      const index = Math.max(0, Math.min(waypoints.length - 1, Math.floor(waypoints.length / 2)));
      const visual = routeVisualStatus(routeId, snapshot, view);
      features.push(feature(
        {
          type: "Point",
          coordinates: localToLngLat(waypoints[index]),
        },
        {
          feature_id: `route-label:${routeId}`,
          object_type: "route",
          object_id: routeId,
          label: `${String(route.label || routeId)} · ${visual.label}`,
          status: visual.status,
        },
        `route-label:${routeId}`,
      ));
    });
    return collection(features);
  }

  function authorizedPathFeatures(snapshot, view) {
    const assets = view === "controller"
      ? snapshot.controller.known_assets
      : snapshot.truth.assets;
    const features = [];

    Object.entries(assets || {}).forEach(([assetId, asset]) => {
      const segments = asset.path_segments || [];
      const startIndex = Number(asset.path_index || 0);
      segments.slice(startIndex).forEach((segment, offset) => {
        features.push(feature(
          {
            type: "LineString",
            coordinates: [
              localToLngLat(segment.from_position),
              localToLngLat(segment.to_position),
            ],
          },
          {
            feature_id: `authorized:${assetId}:${startIndex + offset}`,
            object_type: "asset",
            object_id: assetId,
            asset_id: assetId,
            asset_type: String(asset.asset_type || "asset"),
            route_id: String(segment.route_id || "direct"),
            edge_index: Number(segment.edge_index ?? -1),
            direction: String(segment.direction || "direct"),
            mode: String(segment.mode || "direct"),
            mission_phase: String(asset.mission_phase || "idle"),
          },
          `authorized:${assetId}:${startIndex + offset}`,
        ));
      });
    });

    return collection(features);
  }

  function assetStatusMismatch(assetId, snapshot) {
    const truth = snapshot.truth.assets?.[assetId];
    const known = snapshot.controller.known_assets?.[assetId];
    if (!truth || !known) return true;
    const dx = Number(truth.position.x) - Number(known.position.x);
    const dy = Number(truth.position.y) - Number(known.position.y);
    return Math.hypot(dx, dy) > 0.5 || truth.status !== known.status;
  }

  function assetFeatures(snapshot, view) {
    const assets = view === "controller"
      ? snapshot.controller.known_assets
      : snapshot.truth.assets;

    return collection(Object.entries(assets || {}).map(([assetId, asset]) => {
      const type = String(asset.asset_type || "asset");
      const icon = {
        survey_drone: "DR",
        rescue_boat: "B",
        helicopter: "H",
        ground_team: "GT",
      }[type] || "A";
      const mismatch = view === "difference" && assetStatusMismatch(assetId, snapshot);

      return feature(
        {
          type: "Point",
          coordinates: localToLngLat(asset.position),
        },
        {
          feature_id: `asset:${assetId}`,
          object_type: "asset",
          object_id: assetId,
          asset_id: assetId,
          asset_type: type,
          icon,
          status: String(asset.status || "unknown"),
          mission_phase: String(asset.mission_phase || "idle"),
          resource: Number(asset.resource ?? 0),
          passengers: Number(asset.passenger_count ?? 0),
          heading_degrees: Number(asset.heading_degrees ?? 0),
          mismatch,
          label: `${assetId} · ${String(asset.mission_phase || "idle")}`,
          detail: `resource ${Number(asset.resource ?? 0).toFixed(2)}`,
        },
        `asset:${assetId}`,
      );
    }));
  }

  function groupMismatch(groupId, snapshot) {
    const truth = snapshot.truth.groups?.[groupId];
    const known = snapshot.controller.known_groups?.[groupId];
    if (!truth || !known) return true;
    return Number(truth.people_waiting ?? 0) !== Number(known.people_waiting ?? 0)
      || truth.rescue_phase !== known.rescue_phase
      || truth.cancelled !== known.cancelled;
  }

  function incidentFeatures(snapshot, view) {
    const groups = view === "controller"
      ? snapshot.controller.known_groups
      : snapshot.truth.groups;

    return collection(Object.entries(groups || {}).map(([groupId, group]) => {
      const waiting = Number(group.people_waiting ?? group.people ?? 0);
      const onboard = Number(group.people_onboard ?? 0);
      const delivered = Number(group.people_delivered ?? 0);
      let incidentStatus = "waiting";
      let countLabel = String(waiting);

      if (group.cancelled) {
        incidentStatus = "cancelled";
        countLabel = "×";
      } else if (group.rescued || group.rescue_phase === "delivered") {
        incidentStatus = "rescued";
        countLabel = "✓";
      } else if (onboard > 0 && waiting === 0) {
        incidentStatus = "onboard";
        countLabel = "↗";
      } else if (String(group.condition) === "critical") {
        incidentStatus = "critical";
      } else if (String(group.condition) === "deteriorating") {
        incidentStatus = "deteriorating";
      }

      const mismatch = view === "difference" && groupMismatch(groupId, snapshot);
      return feature(
        {
          type: "Point",
          coordinates: localToLngLat(group.position),
        },
        {
          feature_id: `group:${groupId}`,
          object_type: "group",
          object_id: groupId,
          group_id: groupId,
          label: String(group.label || groupId),
          incident_status: mismatch ? "mismatch" : incidentStatus,
          waiting,
          onboard,
          delivered,
          count_label: countLabel,
          alert_count: Number(group.alert_count ?? 1),
          severity: Number(group.severity ?? 0),
          rescue_phase: String(group.rescue_phase || "waiting"),
          mismatch,
        },
        `group:${groupId}`,
      );
    }));
  }

  function locationFeatures(snapshot, view) {
    const truthAssets = snapshot.truth.assets || {};
    const boat = Object.values(truthAssets).find((asset) => asset.asset_type === "rescue_boat");
    const drone = Object.values(truthAssets).find((asset) => asset.asset_type === "survey_drone");
    const features = [];

    if (boat?.safe_position || boat?.home_position) {
      const delivered = Object.values(snapshot.truth.groups || {})
        .reduce((sum, group) => sum + Number(group.people_delivered || 0), 0);
      features.push(feature(
        {
          type: "Point",
          coordinates: localToLngLat(boat.safe_position || boat.home_position),
        },
        {
          feature_id: "location:safe-transfer-dock",
          object_type: "location",
          object_id: "safe_transfer_dock",
          location_type: "safe_dock",
          icon: "S",
          label: `Safe Transfer Dock · ${delivered} delivered`,
        },
        "location:safe-transfer-dock",
      ));
    }

    if (drone?.home_position) {
      features.push(feature(
        {
          type: "Point",
          coordinates: localToLngLat(drone.home_position),
        },
        {
          feature_id: "location:drone-pad",
          object_type: "location",
          object_id: "drone_pad",
          location_type: "drone_pad",
          icon: "P",
          label: "Drone Pad",
        },
        "location:drone-pad",
      ));
    }

    return collection(features);
  }

  function hazardFeatures(snapshot, view) {
    const features = [];
    Object.entries(snapshot.truth.routes || {}).forEach(([routeId, route]) => {
      const belief = snapshot.controller.route_beliefs?.[routeId];
      let visible = false;
      let position = null;
      let status = "blocked";

      if (view === "truth" || view === "difference") {
        visible = route.open === false;
        position = route.blockage_position;
        status = view === "difference" && belief?.status !== "blocked"
          ? "mismatch"
          : "blocked";
      } else if (belief?.status === "blocked") {
        visible = true;
        const index = Number(belief.blocked_segment_index ?? route.blocked_segment_index ?? 0);
        const a = route.waypoints?.[index];
        const b = route.waypoints?.[Math.min(index + 1, (route.waypoints?.length || 1) - 1)];
        if (a && b) {
          position = {
            x: (Number(a.x) + Number(b.x)) / 2,
            y: (Number(a.y) + Number(b.y)) / 2,
          };
        }
      }

      if (!visible || !position) return;
      features.push(feature(
        {
          type: "Point",
          coordinates: localToLngLat(position),
        },
        {
          feature_id: `hazard:${routeId}`,
          object_type: "route",
          object_id: routeId,
          route_id: routeId,
          status,
          icon: "×",
          label: `${String(route.label || routeId)} obstruction`,
        },
        `hazard:${routeId}`,
      ));
    });
    return collection(features);
  }

  function floodFeatures(snapshot) {
    return collection([
      feature(
        {
          type: "Polygon",
          coordinates: [FLOOD_POLYGON_LOCAL.map(localToLngLat)],
        },
        {
          feature_id: "flood:main",
          water_level: Number(snapshot.truth.global_water_level ?? 0),
          weather: Number(snapshot.truth.weather_severity ?? 0),
          communications: snapshot.truth.communications_available ? "online" : "down",
        },
        "flood:main",
      ),
    ]);
  }

  function addOperationalLayers() {
    Object.values(SOURCE_IDS).forEach(addSource);

    map.addLayer({
      id: "trace-flood-fill",
      type: "fill",
      source: SOURCE_IDS.flood,
      paint: {
        "fill-color": "#5aa7d1",
        "fill-opacity": [
          "interpolate",
          ["linear"],
          ["coalesce", ["get", "water_level"], 0],
          0, 0.10,
          0.5, 0.28,
          1.0, 0.48,
        ],
        "fill-outline-color": "#2f7da7",
      },
    });

    map.addLayer({
      id: "trace-route-casing",
      type: "line",
      source: SOURCE_IDS.routes,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": "rgba(255,255,255,0.92)",
        "line-width": ["interpolate", ["linear"], ["zoom"], 10, 6, 16, 11],
        "line-opacity": 0.95,
      },
    });

    map.addLayer({
      id: "trace-route-lines",
      type: "line",
      source: SOURCE_IDS.routes,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": [
          "match",
          ["coalesce", ["get", "status"], "unknown"],
          "open", "#14865f",
          "blocked", "#bd3434",
          "mismatch", "#b66a00",
          "#8394a1",
        ],
        "line-width": ["interpolate", ["linear"], ["zoom"], 10, 3, 16, 7],
        "line-opacity": 0.92,
      },
    });

    map.addLayer({
      id: "trace-authorized-paths",
      type: "line",
      source: SOURCE_IDS.authorizedPaths,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": "#0c5fa6",
        "line-width": ["interpolate", ["linear"], ["zoom"], 10, 3, 16, 6],
        "line-dasharray": [1.4, 1.1],
        "line-opacity": 0.92,
      },
    });

    map.addLayer({
      id: "trace-route-labels",
      type: "symbol",
      source: SOURCE_IDS.routeLabels,
      layout: {
        "text-field": ["to-string", ["coalesce", ["get", "label"], ""]],
        "text-size": 12,
        "text-font": ["Noto Sans Regular"],
        "text-offset": [0, 1.2],
        "text-anchor": "top",
        "text-allow-overlap": true,
      },
      paint: {
        "text-color": "#183346",
        "text-halo-color": "rgba(255,255,255,0.95)",
        "text-halo-width": 2,
      },
    });

    map.addLayer({
      id: "trace-locations",
      type: "circle",
      source: SOURCE_IDS.locations,
      paint: {
        "circle-radius": 9,
        "circle-color": [
          "match",
          ["coalesce", ["get", "location_type"], "location"],
          "safe_dock", "#76512d",
          "drone_pad", "#7251b5",
          "#405d70",
        ],
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 2,
      },
    });

    map.addLayer({
      id: "trace-location-labels",
      type: "symbol",
      source: SOURCE_IDS.locations,
      layout: {
        "text-field": ["to-string", ["coalesce", ["get", "label"], ""]],
        "text-size": 11,
        "text-offset": [0, 1.5],
        "text-anchor": "top",
        "text-allow-overlap": true,
      },
      paint: {
        "text-color": "#263f51",
        "text-halo-color": "rgba(255,255,255,0.95)",
        "text-halo-width": 2,
      },
    });

    map.addLayer({
      id: "trace-hazards",
      type: "circle",
      source: SOURCE_IDS.hazards,
      paint: {
        "circle-radius": 11,
        "circle-color": [
          "match",
          ["coalesce", ["get", "status"], "blocked"],
          "mismatch", "#b66a00",
          "#bd3434",
        ],
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 2.5,
      },
    });

    map.addLayer({
      id: "trace-hazard-labels",
      type: "symbol",
      source: SOURCE_IDS.hazards,
      layout: {
        "text-field": "×",
        "text-size": 18,
        "text-font": ["Noto Sans Bold"],
        "text-allow-overlap": true,
      },
      paint: { "text-color": "#ffffff" },
    });

    map.addLayer({
      id: "trace-incidents",
      type: "circle",
      source: SOURCE_IDS.incidents,
      paint: {
        "circle-radius": [
          "step",
          ["coalesce", ["get", "waiting"], 0],
          10,
          1, 13,
          5, 16,
          10, 19,
        ],
        "circle-color": [
          "match",
          ["coalesce", ["get", "incident_status"], "waiting"],
          "critical", "#bd3434",
          "deteriorating", "#d96522",
          "rescued", "#14865f",
          "onboard", "#2f80c5",
          "cancelled", "#8394a1",
          "mismatch", "#b66a00",
          "#e98b26",
        ],
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 3,
      },
    });

    map.addLayer({
      id: "trace-incident-counts",
      type: "symbol",
      source: SOURCE_IDS.incidents,
      layout: {
        "text-field": ["to-string", ["coalesce", ["get", "count_label"], ""]],
        "text-size": 12,
        "text-font": ["Noto Sans Bold"],
        "text-allow-overlap": true,
      },
      paint: { "text-color": "#ffffff" },
    });

    map.addLayer({
      id: "trace-incident-labels",
      type: "symbol",
      source: SOURCE_IDS.incidents,
      layout: {
        "text-field": ["to-string", ["coalesce", ["get", "label"], ""]],
        "text-size": 11,
        "text-offset": [1.5, 0],
        "text-anchor": "left",
        "text-allow-overlap": true,
      },
      paint: {
        "text-color": "#263f51",
        "text-halo-color": "rgba(255,255,255,0.96)",
        "text-halo-width": 2,
      },
    });

    map.addLayer({
      id: "trace-assets",
      type: "circle",
      source: SOURCE_IDS.assets,
      paint: {
        "circle-radius": [
          "match",
          ["coalesce", ["get", "asset_type"], "asset"],
          "survey_drone", 10,
          "rescue_boat", 12,
          "helicopter", 12,
          "ground_team", 11,
          10,
        ],
        "circle-color": [
          "case",
          ["boolean", ["get", "mismatch"], false], "#b66a00",
          [
            "match",
            ["coalesce", ["get", "asset_type"], "asset"],
            "survey_drone", "#7251b5",
            "rescue_boat", "#1668b2",
            "helicopter", "#b66a00",
            "ground_team", "#14865f",
            "#405d70",
          ],
        ],
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 2.5,
      },
    });

    map.addLayer({
      id: "trace-asset-icons",
      type: "symbol",
      source: SOURCE_IDS.assets,
      layout: {
        "text-field": ["to-string", ["coalesce", ["get", "icon"], "A"]],
        "text-size": 10,
        "text-font": ["Noto Sans Bold"],
        "text-allow-overlap": true,
      },
      paint: { "text-color": "#ffffff" },
    });

    map.addLayer({
      id: "trace-asset-labels",
      type: "symbol",
      source: SOURCE_IDS.assets,
      layout: {
        "text-field": ["to-string", ["coalesce", ["get", "label"], ""]],
        "text-size": 11,
        "text-offset": [1.5, -0.4],
        "text-anchor": "left",
        "text-allow-overlap": true,
      },
      paint: {
        "text-color": "#183346",
        "text-halo-color": "rgba(255,255,255,0.96)",
        "text-halo-width": 2,
      },
    });

    registerSelection("trace-route-lines");
    registerSelection("trace-route-labels");
    registerSelection("trace-assets");
    registerSelection("trace-asset-labels");
    registerSelection("trace-incidents");
    registerSelection("trace-incident-labels");
    registerSelection("trace-hazards");
    registerSelection("trace-locations");
  }

  function registerSelection(layerId) {
    map.on("mouseenter", layerId, () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", layerId, () => { map.getCanvas().style.cursor = ""; });
    map.on("click", layerId, (event) => {
      const selected = event.features?.[0]?.properties;
      if (!selected?.object_type || !selected?.object_id) return;
      selectObject(String(selected.object_type), String(selected.object_id));
    });
  }

  function fitLocalScenario() {
    if (!map || fitted) return;
    const southwest = localToLngLat({
      x: DISPLAY_REFERENCE.localBounds.xMin,
      y: DISPLAY_REFERENCE.localBounds.yMin,
    });
    const northeast = localToLngLat({
      x: DISPLAY_REFERENCE.localBounds.xMax,
      y: DISPLAY_REFERENCE.localBounds.yMax,
    });
    map.fitBounds([southwest, northeast], {
      padding: { top: 70, right: 70, bottom: 70, left: 70 },
      duration: 0,
      maxZoom: 15.5,
    });
    map.setPitch(DISPLAY_REFERENCE.pitch);
    map.setBearing(DISPLAY_REFERENCE.bearing);
    fitted = true;
  }

  function featureMap(featureCollection) {
    return new Map(featureCollection.features.map((item) => [
      String(item.properties.feature_id),
      item,
    ]));
  }

  function interpolateAssetCollection(previous, target, amount) {
    return collection(target.features.map((targetFeature) => {
      const id = String(targetFeature.properties.feature_id);
      const previousFeature = previous.get(id);
      if (!previousFeature || previousFeature.geometry.type !== "Point") {
        return targetFeature;
      }
      const [fromLon, fromLat] = previousFeature.geometry.coordinates;
      const [toLon, toLat] = targetFeature.geometry.coordinates;
      return {
        ...targetFeature,
        geometry: {
          type: "Point",
          coordinates: [
            fromLon + (toLon - fromLon) * amount,
            fromLat + (toLat - fromLat) * amount,
          ],
        },
      };
    }));
  }

  function updateAssetsAnimated(targetCollection) {
    if (assetAnimationFrame !== null) {
      cancelAnimationFrame(assetAnimationFrame);
      assetAnimationFrame = null;
    }

    const targetMap = featureMap(targetCollection);
    if (previousAssetFeatures.size === 0) {
      setSourceData(SOURCE_IDS.assets, targetCollection);
      previousAssetFeatures = targetMap;
      return;
    }

    const start = performance.now();
    const duration = 320;
    const previous = previousAssetFeatures;

    const frame = (now) => {
      const raw = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - raw, 3);
      setSourceData(
        SOURCE_IDS.assets,
        interpolateAssetCollection(previous, targetCollection, eased),
      );
      if (raw < 1) {
        assetAnimationFrame = requestAnimationFrame(frame);
      } else {
        assetAnimationFrame = null;
        previousAssetFeatures = targetMap;
      }
    };

    assetAnimationFrame = requestAnimationFrame(frame);
  }

  function initialize(options = {}) {
    selectObject = typeof options.onSelectObject === "function"
      ? options.onSelectObject
      : () => {};

    const status = document.getElementById(options.statusId || "mapLoadStatus");
    if (typeof maplibregl === "undefined") {
      if (status) {
        status.textContent = "MapLibre did not load. Check the network connection.";
        status.classList.remove("ready");
      }
      return Promise.reject(new Error("maplibregl is not available"));
    }

    map = new maplibregl.Map({
      container: options.containerId || "map",
      style: options.styleUrl || DISPLAY_REFERENCE.styleUrl,
      center: localToLngLat({ x: 50, y: 40 }),
      zoom: 13,
      pitch: DISPLAY_REFERENCE.pitch,
      bearing: DISPLAY_REFERENCE.bearing,
      maxPitch: DISPLAY_REFERENCE.maxPitch,
      antialias: true,
    });

    map.addControl(new maplibregl.NavigationControl({
      showZoom: true,
      showCompass: true,
      visualizePitch: true,
    }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: "metric" }), "bottom-right");

    return new Promise((resolve, reject) => {
      map.once("load", () => {
        try {
          addOperationalLayers();
          fitLocalScenario();
          ready = true;
          if (status) {
            status.textContent = "Operational layers ready";
            status.classList.add("ready");
          }
          resolve(map);
        } catch (error) {
          if (status) {
            status.textContent = "Operational-layer setup failed. See console.";
            status.classList.remove("ready");
          }
          reject(error);
        }
      });

      map.on("error", (event) => {
        // Base-map styles can emit non-fatal data warnings. Preserve them in
        // the console, but only mark setup failed before the map is ready.
        console.warn("MapLibre event", event.error || event);
        if (!ready && status) {
          status.textContent = "Map warning. See browser console.";
        }
      });
    });
  }

  function update(snapshot, view = "controller") {
    if (!ready || !map || !snapshot) return false;

    setSourceData(SOURCE_IDS.flood, floodFeatures(snapshot));
    setSourceData(SOURCE_IDS.routes, routeFeatures(snapshot, view));
    setSourceData(SOURCE_IDS.routeLabels, routeLabelFeatures(snapshot, view));
    setSourceData(SOURCE_IDS.authorizedPaths, authorizedPathFeatures(snapshot, view));
    setSourceData(SOURCE_IDS.hazards, hazardFeatures(snapshot, view));
    setSourceData(SOURCE_IDS.incidents, incidentFeatures(snapshot, view));
    setSourceData(SOURCE_IDS.locations, locationFeatures(snapshot, view));
    updateAssetsAnimated(assetFeatures(snapshot, view));
    map.resize();
    return true;
  }

  function resize() {
    map?.resize();
  }

  function resetView() {
    fitted = false;
    fitLocalScenario();
  }

  window.TraceGeoMap = Object.freeze({
    initialize,
    update,
    resize,
    resetView,
    isReady: () => ready,
    getMap: () => map,
    localToLngLat,
    displayReference: DISPLAY_REFERENCE,
  });
})();
