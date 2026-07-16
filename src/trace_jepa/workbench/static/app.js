const $ = (id) => document.getElementById(id);
const appState = {
  snapshot: null,
  view: "controller",
  selected: null,
  history: [],
  ws: null,
  lastAssetPositions: new Map(),
};


function mapViewLabel(view) {
  if (view === "truth") return "Simulation ground truth";
  if (view === "difference") return "Knowledge differences";
  return "Mission Controller knowledge";
}

function initializeOperationalMap() {
  if (!window.TraceGeoMap) {
    const status = $("mapLoadStatus");
    if (status) status.textContent = "GeoJSON overlay module did not load.";
    return;
  }

  window.TraceGeoMap.initialize({
    containerId: "map",
    statusId: "mapLoadStatus",
    onSelectObject: selectObject,
  }).then(() => {
    if (appState.snapshot) renderMap(appState.snapshot);
    console.info("MapLibre operational map initialized", {
      reference: window.TraceGeoMap.displayReference,
    });
  }).catch((error) => {
    console.error("Operational map initialization failed", error);
  });
}

function value(id) { return $(id).value; }
function number(id) { return Number($(id).value); }

async function post(path, body = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
  return response.json();
}

async function inject(eventType, scenarioLevel, payload, visibility = "both") {
  return post("/api/events", {
    event_type: eventType,
    scenario_level: scenarioLevel,
    visibility,
    payload,
  });
}

function bindRange(inputId, outputId, digits = 2) {
  const input = $(inputId), output = $(outputId);
  const update = () => { output.textContent = Number(input.value).toFixed(digits); };
  input.addEventListener("input", update);
  update();
}

function setupTabs() {
  document.querySelectorAll(".scenario-tab").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".scenario-tab").forEach((item) => item.classList.remove("active"));
      document.querySelectorAll(".scenario-pane").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      $(`tab-${button.dataset.tab}`).classList.add("active");
    });
  });
  document.querySelectorAll(".lower-tab").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".lower-tab").forEach((item) => item.classList.remove("active"));
      document.querySelectorAll(".lower-pane").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      $(`lower-${button.dataset.lower}`).classList.add("active");
      if (button.dataset.lower === "metrics") renderChart();
    });
  });
}

function setupControls() {
  setupTabs();
  [
    ["s1Accuracy", "s1AccuracyOut"], ["s1Noise", "s1NoiseOut"],
    ["s1Packet", "s1PacketOut"], ["s1Ood", "s1OodOut"],
    ["s2Rain", "s2RainOut"], ["s2Inflow", "s2InflowOut"],
    ["shockSeverity", "shockSeverityOut"],
    ["s5Endurance", "s5EnduranceOut"], ["s5Quality", "s5QualityOut"],
    ["s5Weather", "s5WeatherOut"],
  ].forEach(([input, output]) => bindRange(input, output));

  $("startBtn").onclick = () => post("/api/control/start");
  $("pauseBtn").onclick = () => post("/api/control/pause");
  $("stepBtn").onclick = () => post("/api/control/step", { dt: 1.0 });
  $("planBtn").onclick = () => post("/api/plan");
  $("resetBtn").onclick = async () => {
    if (confirm("Reset this run and clear its event, TRACE, evidence, and commitment logs?")) {
      appState.history = [];
      appState.lastAssetPositions.clear();
      await post("/api/control/reset");
      $("callResult").className = "call-result";
      $("callResult").textContent = "No incident submitted yet.";
    }
  };
  $("exportBtn").onclick = async () => {
    const result = await post("/api/export");
    alert(`Run manifest written to:\n${result.path}`);
  };
  $("speedRange").oninput = () => {
    $("speedValue").textContent = `${Number($("speedRange").value).toFixed(1)}×`;
  };
  $("speedRange").onchange = () => post("/api/control/speed", { speed: number("speedRange") });
  $("authorityToggle").onchange = () => inject(
    "COMMANDER_AUTHORITY", "CORE", { present: $("authorityToggle").checked }
  );

  $("submitCallBtn").onclick = async () => {
    const resultBox = $("callResult");
    resultBox.className = "call-result pending";
    resultBox.textContent = "Submitting alert and running TRACE reasoning…";
    try {
      const result = await post("/api/emergency-call", {
        location_label: value("callLocation"), x: number("callX"), y: number("callY"),
        people: number("callPeople"), severity: number("callSeverity"),
        deadline_s: number("callDeadline"),
        count_semantics: value("callCountSemantics"),
      });
      const action = result.resolution === "created"
        ? "Created"
        : result.resolution === "merged" ? "Merged into" : "Updated";
      resultBox.className = "call-result success";
      resultBox.textContent = `${action} ${result.group_id}: ${result.people_waiting} waiting, ${result.people_onboard} onboard, ${result.people_delivered} delivered · alert ${result.alert_count}.`;
    } catch (error) {
      resultBox.className = "call-result error";
      resultBox.textContent = `Alert rejected: ${error.message}`;
    }
  };

  $("applyS1Btn").onclick = () => inject("SET_S1_PARAMETERS", "S1", {
    drone_report_accuracy: number("s1Accuracy"), sensor_noise: number("s1Noise"),
    observation_latency_s: number("s1Latency"), packet_loss: number("s1Packet"),
    ood_severity: number("s1Ood"), seed: number("s1Seed"),
  });
  $("applyS2Btn").onclick = () => inject("SET_S2_PARAMETERS", "S2", {
    rain_intensity: number("s2Rain"), upstream_inflow: number("s2Inflow"),
    water_rise_rate: number("s2Rise"), route_closure_depth: number("s2Closure"),
    clearance_horizon_s: number("s2Horizon"), observation_freshness_s: number("s2Freshness"),
  });
  $("applyS3Btn").onclick = () => inject("SET_S3_PARAMETERS", "S3", {
    mission_budget: number("s3Budget"), severity_weight: number("s3SeverityWeight"),
    deadline_weight: number("s3DeadlineWeight"), risk_weight: number("s3RiskWeight"),
  });
  $("addGroupBtn").onclick = () => inject("ADD_GROUP", "S3", {
    group_id: `group_${Date.now()}`, label: value("groupLabel"),
    position: { x: number("groupX"), y: number("groupY") },
    people: number("groupPeople"), severity: number("groupSeverity"),
    deadline_s: number("groupDeadline"), discovered: true, rescued: false,
    assigned_asset_id: null, condition: "stable",
  });
  $("addAssetBtn").onclick = () => {
    const type = value("assetType"), position = { x: number("assetX"), y: number("assetY") };
    return inject("ADD_ASSET", "S3", {
      asset_id: `${type}_${Date.now()}`, asset_type: type,
      position, home_position: position,
      capacity: number("assetCapacity"), speed: number("assetSpeed"),
      resource: number("assetResource"),
      operating_cost: type === "helicopter" ? 18 : type === "rescue_boat" ? 5 : 2,
      weather_tolerance: type === "helicopter" ? 0.65 : type === "survey_drone" ? 0.70 : 0.85,
      status: "available", assigned_group_id: null, assigned_route_id: null,
      action_type: null, path: [], path_segments: [], path_index: 0, target: null,
      action_started_at: null, authorization_record_id: null,
      authorization_record_version: null, interruption_reason: null,
    });
  };
  $("injectShockBtn").onclick = () => inject("INJECT_SHOCK", "S4", {
    shock_type: value("shockType"), target: value("shockTarget") || null,
    severity: number("shockSeverity"),
  }, value("shockVisibility"));
  $("applyS5Btn").onclick = () => inject("SET_S5_PARAMETERS", "S5", {
    default_drone_endurance: number("s5Endurance"), sensor_quality: number("s5Quality"),
    sector_weather: number("s5Weather"), value_of_information_weight: number("s5Voi"),
  });
  $("requestSurveyBtn").onclick = () => inject("REQUEST_SURVEY", "S5", {
    route_id: value("surveyRoute"), requested_by: "operator_ui",
  });

  document.querySelectorAll("#viewToggle button").forEach((button) => {
    button.onclick = () => {
      document.querySelectorAll("#viewToggle button").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      appState.view = button.dataset.view;
      if (appState.snapshot) renderMap(appState.snapshot);
    };
  });
}

function connectWebSocket() {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${location.host}/ws`);
  appState.ws = ws;
  ws.onopen = () => {
    $("connectionBadge").textContent = "live";
    $("connectionBadge").className = "status-pill online";
  };
  ws.onclose = () => {
    $("connectionBadge").textContent = "reconnecting";
    $("connectionBadge").className = "status-pill offline";
    setTimeout(connectWebSocket, 1200);
  };
  ws.onmessage = (event) => update(JSON.parse(event.data));
}

function update(snapshot) {
  appState.snapshot = snapshot;
  $("simTime").textContent = Number(snapshot.truth.simulation_time).toFixed(1);
  $("runBadge").textContent = snapshot.running ? "running" : "paused";
  $("authorityToggle").checked = snapshot.config.commander_authority_present;
  $("speedRange").value = snapshot.config.simulation_speed;
  $("speedValue").textContent = `${Number(snapshot.config.simulation_speed).toFixed(1)}×`;
  renderDecision(snapshot);
  renderMap(snapshot);
  renderReasoning(snapshot.controller.latest_reasoning);
  renderTrace(snapshot);
  renderTimeline(snapshot.recent_events);
  renderStats(snapshot.metrics, snapshot);
  addHistory(snapshot);
  if (document.querySelector('[data-lower="metrics"].active')) renderChart();
  if (appState.selected) renderSelected();
}

function renderDecision(snapshot) {
  const decision = snapshot.controller.last_selected_plan;
  const banner = $("decisionBanner");
  if (!decision) {
    banner.className = "decision-banner neutral";
    $("decisionTitle").textContent = "No plan has been evaluated yet.";
    $("decisionReason").textContent = "Submit a call or run a reasoning cycle.";
    return;
  }
  const value = decision.decision || "hold";
  banner.className = `decision-banner ${value}`;
  $("decisionTitle").textContent = `${value.toUpperCase()} · ${decision.plan_name || decision.plan_id}`;
  $("decisionReason").textContent = decision.reason || "Decision recorded by TRACE consumer policy.";
}

function mapPoint(position) {
  const left = 45, top = 34, width = 910, height = 565;
  return { x: left + (position.x / 100) * width, y: top + ((80 - position.y) / 80) * height };
}
function polyline(points) { return points.map((p) => { const q = mapPoint(p); return `${q.x},${q.y}`; }).join(" "); }
function svgEl(name, attrs = {}) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attrs).forEach(([key, val]) => element.setAttribute(key, val));
  return element;
}
function appendTitle(element, text) {
  const title = svgEl("title"); title.textContent = text; element.appendChild(title);
}

function routeStatus(routeId, snapshot) {
  const truth = snapshot.truth.routes[routeId];
  const belief = snapshot.controller.route_beliefs[routeId];
  const truthStatus = truth.open ? "open" : "blocked";
  const beliefStatus = belief?.status || "unknown";
  if (appState.view === "truth") return { status: truthStatus, label: truthStatus };
  if (appState.view === "controller") return { status: beliefStatus, label: beliefStatus };
  const mismatch = beliefStatus === "unknown" || beliefStatus !== truthStatus;
  return { status: mismatch ? "mismatch" : truthStatus, label: `${beliefStatus} / ${truthStatus}` };
}

function movingGroup(assetId, position) {
  const outer = svgEl("g", { class: "moving-asset", "data-asset": assetId });
  const previous = appState.lastAssetPositions.get(assetId);
  outer.setAttribute("transform", `translate(${position.x} ${position.y})`);
  if (previous && (Math.abs(previous.x - position.x) > 0.01 || Math.abs(previous.y - position.y) > 0.01)) {
    outer.appendChild(svgEl("animateTransform", {
      attributeName: "transform", type: "translate",
      from: `${previous.x} ${previous.y}`, to: `${position.x} ${position.y}`,
      dur: "0.32s", fill: "freeze", calcMode: "spline", keySplines: "0.2 0.7 0.2 1",
    }));
  }
  appState.lastAssetPositions.set(assetId, position);
  return outer;
}

function droneIcon(assetId, asset, position, fill) {
  const outer = movingGroup(assetId, position);
  const heading = -(Number(asset.heading_degrees || 0));
  const rotated = svgEl("g", { transform: `rotate(${heading})`, class: "asset-icon drone-icon" });
  const body = svgEl("g", { class: "drone-bob" });
  body.appendChild(svgEl("rect", { x: -7, y: -5, width: 14, height: 10, rx: 4, fill, stroke: "#fff", "stroke-width": 1.5 }));
  body.appendChild(svgEl("circle", { cx: 0, cy: 2, r: 3.2, fill: "#172a38", stroke: "#bde3f4", "stroke-width": 1 }));
  [[-13,-9],[13,-9],[-13,9],[13,9]].forEach(([x,y], index) => {
    body.appendChild(svgEl("line", { x1: x * .35, y1: y * .35, x2: x, y2: y, stroke: fill, "stroke-width": 2.5 }));
    const rotor = svgEl("g", { transform: `translate(${x} ${y})`, class: `drone-rotor rotor-${index}` });
    rotor.appendChild(svgEl("line", { x1: -6, y1: 0, x2: 6, y2: 0, stroke: "#173142", "stroke-width": 1.5, "stroke-linecap": "round" }));
    rotor.appendChild(svgEl("line", { x1: 0, y1: -3, x2: 0, y2: 3, stroke: "#173142", "stroke-width": 1.1, "stroke-linecap": "round" }));
    rotor.appendChild(svgEl("circle", { cx: 0, cy: 0, r: 1.8, fill: "#fff", stroke: fill, "stroke-width": 1 }));
    body.appendChild(rotor);
  });
  rotated.appendChild(body); outer.appendChild(rotated);
  appendTitle(outer, `${assetId}: ${asset.status}, ${asset.mission_phase || "idle"}`);
  return outer;
}

function boatIcon(assetId, asset, position, fill) {
  const outer = movingGroup(assetId, position);
  const heading = -(Number(asset.heading_degrees || 0));
  const rotated = svgEl("g", { transform: `rotate(${heading})`, class: "asset-icon boat-icon" });
  const bob = svgEl("g", { class: "boat-bob" });
  const moving = asset.status === "moving";
  if (moving) {
    const wake = svgEl("g", { class: "boat-wake" });
    [-5, 2, 9].forEach((y, i) => wake.appendChild(svgEl("path", {
      d: `M -38 ${y} C -30 ${y-4} -23 ${y+4} -16 ${y}`,
      fill: "none", stroke: i === 1 ? "#a9def3" : "#d4eef8", "stroke-width": 2,
      "stroke-linecap": "round", "stroke-dasharray": "7 5",
    })));
    bob.appendChild(wake);
  }
  bob.appendChild(svgEl("path", { d: "M -19 1 L 19 1 L 13 10 L -13 10 Z", fill, stroke: "#fff", "stroke-width": 1.7 }));
  bob.appendChild(svgEl("rect", { x: -5, y: -8, width: 14, height: 9, rx: 2, fill: "#f7fbfd", stroke: fill, "stroke-width": 1.5 }));
  bob.appendChild(svgEl("rect", { x: -2, y: -6, width: 4, height: 3, fill: "#75b9da" }));
  bob.appendChild(svgEl("rect", { x: 4, y: -6, width: 3, height: 3, fill: "#75b9da" }));
  bob.appendChild(svgEl("line", { x1: 11, y1: -8, x2: 11, y2: -15, stroke: "#173142", "stroke-width": 1.5 }));
  bob.appendChild(svgEl("circle", { cx: 11, cy: -16, r: 1.7, fill: "#e98b26" }));
  rotated.appendChild(bob); outer.appendChild(rotated);
  if (Number(asset.passenger_count || 0) > 0) {
    outer.appendChild(svgEl("circle", { cx: 17, cy: -18, r: 10, class: "passenger-badge" }));
    const count = svgEl("text", { x: 17, y: -14.5, "text-anchor": "middle", class: "passenger-count" });
    count.textContent = asset.passenger_count; outer.appendChild(count);
  }
  appendTitle(outer, `${assetId}: ${asset.status}, ${asset.mission_phase || "idle"}, passengers ${asset.passenger_count || 0}`);
  return outer;
}

function genericAssetIcon(assetId, asset, position, fill) {
  const outer = movingGroup(assetId, position);
  const rotated = svgEl("g", { transform: `rotate(${-Number(asset.heading_degrees || 0)})`, class: "asset-icon" });
  if (asset.asset_type === "helicopter") {
    rotated.appendChild(svgEl("ellipse", { cx: 0, cy: 0, rx: 13, ry: 6, fill, stroke: "#fff", "stroke-width": 1.5 }));
    rotated.appendChild(svgEl("line", { x1: -19, y1: -9, x2: 19, y2: -9, stroke: "#173142", "stroke-width": 2, class: "helicopter-rotor" }));
    rotated.appendChild(svgEl("line", { x1: 10, y1: 0, x2: 22, y2: 5, stroke: fill, "stroke-width": 3 }));
  } else {
    rotated.appendChild(svgEl("circle", { cx: 0, cy: 0, r: 12, fill, stroke: "#fff", "stroke-width": 2.5 }));
    const text = svgEl("text", { x: 0, y: 4, "text-anchor": "middle", fill: "#fff", "font-size": 10, "font-weight": 850 });
    text.textContent = asset.asset_type === "ground_team" ? "GT" : "A"; rotated.appendChild(text);
  }
  outer.appendChild(rotated);
  appendTitle(outer, `${assetId}: ${asset.status}`);
  return outer;
}

function drawAsset(svg, assetId, asset) {
  const p = mapPoint(asset.position);
  const colorsByType = { survey_drone: "#7251b5", rescue_boat: "#1668b2", helicopter: "#b66a00", ground_team: "#14865f" };
  const fill = ["grounded","depleted","stranded"].includes(asset.status) ? "#bd3434" : colorsByType[asset.asset_type];
  let icon;
  if (asset.asset_type === "survey_drone") icon = droneIcon(assetId, asset, p, fill);
  else if (asset.asset_type === "rescue_boat") icon = boatIcon(assetId, asset, p, fill);
  else icon = genericAssetIcon(assetId, asset, p, fill);
  icon.addEventListener("click", () => selectObject("asset", assetId));
  svg.appendChild(icon);

  const labelYOffset = asset.asset_type === "survey_drone" ? 28 : -24;
  const label = svgEl("text", { x: p.x + 24, y: p.y + labelYOffset, class: "map-label" });
  label.textContent = assetId; svg.appendChild(label);
  const sub = svgEl("text", { x: p.x + 24, y: p.y + labelYOffset + 14, class: "map-small" });
  const phase = asset.mission_phase || "idle";
  sub.textContent = `${phase} · resource ${Number(asset.resource).toFixed(2)}`; svg.appendChild(sub);
}

function renderMap(snapshot) {
  $("mapSubtitle").textContent = mapViewLabel(appState.view);
  if (window.TraceGeoMap?.isReady()) {
    window.TraceGeoMap.update(snapshot, appState.view);
    return;
  }
  renderLegacyMap(snapshot);
}

function renderLegacyMap(snapshot) {
  const svg = $("mapSvg");
  svg.replaceChildren();
  svg.appendChild(svgEl("rect", { x: 0, y: 0, width: 1000, height: 650, fill: "#f4f8fa" }));
  const floodPoints = [[0,24],[18,22],[36,31],[52,28],[72,38],[100,32],[100,80],[0,80]].map(([x,y]) => mapPoint({x,y}));
  svg.appendChild(svgEl("polygon", {
    points: floodPoints.map((p) => `${p.x},${p.y}`).join(" "),
    fill: "#b9dced", opacity: .72, stroke: "#64a5c5", "stroke-width": 2,
  }));
  const waterText = svgEl("text", { x: 58, y: 55, class: "map-water-label" });
  waterText.textContent = `Water ${Number(snapshot.truth.global_water_level).toFixed(3)} · Weather ${Number(snapshot.truth.weather_severity).toFixed(2)} · Communications ${snapshot.truth.communications_available ? "online" : "down"}`;
  svg.appendChild(waterText);

  const colors = { open: "#14865f", blocked: "#bd3434", unknown: "#8394a1", mismatch: "#b66a00" };
  Object.entries(snapshot.truth.routes).forEach(([routeId, route]) => {
    const visual = routeStatus(routeId, snapshot);
    const line = svgEl("polyline", { points: polyline(route.waypoints), class: "map-route", stroke: colors[visual.status] });
    line.addEventListener("click", () => selectObject("route", routeId));
    svg.appendChild(line);

    if (appState.view !== "controller") {
      (route.edge_open || []).forEach((isOpen, index) => {
        if (isOpen) return;
        const a = mapPoint(route.waypoints[index]), b = mapPoint(route.waypoints[index + 1]);
        svg.appendChild(svgEl("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, class: "map-edge-closed" }));
      });
      if (route.blockage_position && !route.open) {
        const h = mapPoint(route.blockage_position);
        svg.appendChild(svgEl("circle", { cx: h.x, cy: h.y, r: 9, class: "map-hazard" }));
        const x = svgEl("text", { x: h.x, y: h.y + 5, "text-anchor": "middle", fill: "#fff", "font-size": 13, "font-weight": 900 });
        x.textContent = "×"; svg.appendChild(x);
      }
    }
    const routeLabelIndex = Math.max(1, Math.floor(route.waypoints.length / 2) - 1);
    const mid = mapPoint(route.waypoints[routeLabelIndex]);
    const routeLabelOffset = routeId === "south_detour" ? { x: 8, y: 22 } : { x: 8, y: -12 };
    const label = svgEl("text", { x: mid.x + routeLabelOffset.x, y: mid.y + routeLabelOffset.y, class: "map-label" });
    label.textContent = `${route.label} · ${visual.label}`; svg.appendChild(label);
  });

  // The safe-transfer dock is the logical completion point. It currently
  // shares the rescue-base coordinate, but remains a distinct mission object.
  const boatTruth = Object.values(snapshot.truth.assets).find((asset) => asset.asset_type === "rescue_boat");
  if (boatTruth?.safe_position || boatTruth?.home_position) {
    const dock = mapPoint(boatTruth.safe_position || boatTruth.home_position);
    const deliveredAtDock = Object.values(snapshot.truth.groups)
      .reduce((sum, group) => sum + Number(group.people_delivered || 0), 0);
    svg.appendChild(svgEl("line", { x1: dock.x - 19, y1: dock.y + 18, x2: dock.x + 24, y2: dock.y + 18, class: "safe-dock-line" }));
    svg.appendChild(svgEl("rect", { x: dock.x - 18, y: dock.y + 12, width: 36, height: 7, rx: 2, class: "safe-dock" }));
    const dockLabel = svgEl("text", { x: dock.x - 24, y: dock.y + 38, class: "map-label" });
    dockLabel.textContent = `Safe transfer dock · ${deliveredAtDock} delivered`; svg.appendChild(dockLabel);
  }

  Object.entries(snapshot.truth.assets).forEach(([assetId, truthAsset]) => {
    const asset = appState.view === "controller" ? snapshot.controller.known_assets[assetId] : truthAsset;
    if (!asset) return;
    if (asset.path_segments?.length) {
      asset.path_segments.slice(asset.path_index || 0).forEach((segment) => {
        const a = mapPoint(segment.from_position), b = mapPoint(segment.to_position);
        svg.appendChild(svgEl("line", {
          x1: a.x, y1: a.y, x2: b.x, y2: b.y,
          stroke: "#1668b2", "stroke-width": 3, "stroke-dasharray": "9 7", opacity: .78,
          class: "authorized-path",
        }));
      });
    }
    drawAsset(svg, assetId, asset);
  });

  Object.entries(snapshot.truth.groups).forEach(([groupId, truthGroup]) => {
    const group = appState.view === "controller" ? snapshot.controller.known_groups[groupId] : truthGroup;
    if (!group) return;

    const waiting = Number(group.people_waiting ?? group.people ?? 0);
    const p = mapPoint(group.position);
    const anchor = p.x > 820 ? "end" : "start", offset = p.x > 820 ? -24 : 24;

    // Preserve the incident location after pickup. People in transit are shown
    // on the boat; the site marker changes state instead of moving with it.
    if (group.cancelled) {
      const cancelled = svgEl("circle", { cx: p.x, cy: p.y, r: 12, class: "incident-complete cancelled" });
      cancelled.addEventListener("click", () => selectObject("group", groupId));
      svg.appendChild(cancelled);
      const x = svgEl("text", { x: p.x, y: p.y + 5, "text-anchor": "middle", class: "incident-complete-mark" });
      x.textContent = "×"; svg.appendChild(x);
      const label = svgEl("text", { x: p.x + offset, y: p.y + 4, class: "map-label", "text-anchor": anchor });
      label.textContent = `${group.label} · cancelled`; svg.appendChild(label);
      return;
    }

    if (group.rescued || group.rescue_phase === "delivered") {
      const completed = svgEl("circle", { cx: p.x, cy: p.y, r: 12, class: "incident-complete rescued" });
      completed.addEventListener("click", () => selectObject("group", groupId));
      svg.appendChild(completed);
      const check = svgEl("text", { x: p.x, y: p.y + 4.5, "text-anchor": "middle", class: "incident-complete-mark" });
      check.textContent = "✓"; svg.appendChild(check);
      const label = svgEl("text", { x: p.x + offset, y: p.y - 1, class: "map-label", "text-anchor": anchor });
      label.textContent = `${group.label} · rescued`; svg.appendChild(label);
      const sub = svgEl("text", { x: p.x + offset, y: p.y + 14, class: "map-small", "text-anchor": anchor });
      sub.textContent = `${group.people_delivered || 0} delivered to safe dock`; svg.appendChild(sub);
      return;
    }

    if (group.people_onboard > 0 && waiting === 0) {
      const pickedUp = svgEl("circle", { cx: p.x, cy: p.y, r: 12, class: "incident-complete onboard" });
      pickedUp.addEventListener("click", () => selectObject("group", groupId));
      svg.appendChild(pickedUp);
      const check = svgEl("text", { x: p.x, y: p.y + 4.5, "text-anchor": "middle", class: "incident-complete-mark" });
      check.textContent = "↗"; svg.appendChild(check);
      const label = svgEl("text", { x: p.x + offset, y: p.y - 1, class: "map-label", "text-anchor": anchor });
      label.textContent = `${group.label} · pickup complete`; svg.appendChild(label);
      const sub = svgEl("text", { x: p.x + offset, y: p.y + 14, class: "map-small", "text-anchor": anchor });
      sub.textContent = `${group.people_onboard} onboard · en route to safety`; svg.appendChild(sub);
      return;
    }

    if (waiting <= 0) return;

    const fill = group.condition === "critical" ? "#bd3434" : group.condition === "deteriorating" ? "#d96522" : "#e98b26";
    const circle = svgEl("circle", { cx: p.x, cy: p.y, r: 17, fill, stroke: "#fff", "stroke-width": 3, class: "map-group incident-pulse" });
    circle.addEventListener("click", () => selectObject("group", groupId)); svg.appendChild(circle);
    const count = svgEl("text", { x: p.x, y: p.y + 5, "text-anchor": "middle", fill: "#fff", "font-size": 12, "font-weight": 850 });
    count.textContent = waiting; svg.appendChild(count);
    if (Number(group.alert_count || 1) > 1) {
      svg.appendChild(svgEl("circle", { cx: p.x + 15, cy: p.y - 15, r: 8, class: "incident-alert-badge" }));
      const alerts = svgEl("text", { x: p.x + 15, y: p.y - 12, "text-anchor": "middle", class: "incident-alert-count" });
      alerts.textContent = group.alert_count; svg.appendChild(alerts);
    }
    const label = svgEl("text", { x: p.x + offset, y: p.y - 3, class: "map-label", "text-anchor": anchor });
    label.textContent = group.label; svg.appendChild(label);
    const sub = svgEl("text", { x: p.x + offset, y: p.y + 13, class: "map-small", "text-anchor": anchor });
    sub.textContent = `${group.rescue_phase} · ${waiting} waiting · alerts ${group.alert_count || 1}`; svg.appendChild(sub);
  });
}

function renderReasoning(cycle) {
  const summary = $("changeSummary"), flow = $("reasoningFlow");
  if (!cycle) {
    summary.className = "change-summary empty";
    summary.textContent = "No user change has been applied yet.";
    flow.innerHTML = "";
    return;
  }
  summary.className = "change-summary";
  const chips = (cycle.changes || []).map((change) => `<span class="change-chip">${escapeHtml(change.field)}: ${escapeHtml(shortValue(change.before))} → ${escapeHtml(shortValue(change.after))}</span>`).join("");
  summary.innerHTML = `<strong>${escapeHtml(cycle.scenario_level)} · ${escapeHtml(cycle.trigger_label)}</strong><div>${chips || '<span class="change-chip">event applied</span>'}</div>`;
  flow.innerHTML = (cycle.steps || []).map((step, index) => {
    const detail = step.details?.decision_changes?.length ? step.details.decision_changes.join("; ") : step.details?.trace_update ? step.details.trace_update : "";
    return `<div class="reasoning-step ${escapeHtml(step.status)}">
      <div class="step-index">${index + 1}</div>
      <div><div class="step-title">${escapeHtml(step.title)}</div><div class="step-summary">${escapeHtml(step.summary)}</div>${detail ? `<div class="step-detail">${escapeHtml(detail)}</div>` : ""}</div>
    </div>`;
  }).join("");
}

function shortValue(value) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  if (typeof value === "number") return Number(value).toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
  return String(value);
}

function selectObject(kind, id) { appState.selected = { kind, id }; renderSelected(); }
function renderSelected() {
  if (!appState.snapshot || !appState.selected) return;
  const { kind, id } = appState.selected, snapshot = appState.snapshot;
  let data = null;
  if (kind === "route") data = { truth: snapshot.truth.routes[id], controller_belief: snapshot.controller.route_beliefs[id] };
  if (kind === "asset") data = { truth: snapshot.truth.assets[id], controller: snapshot.controller.known_assets[id] };
  if (kind === "group") data = { truth: snapshot.truth.groups[id], controller: snapshot.controller.known_groups[id] };
  $("objectInspector").textContent = JSON.stringify({ kind, id, ...data }, null, 2);
}

function lastDecision(record) {
  const actions = record.consumer_actions || [];
  return actions.length ? actions[actions.length - 1].decision : record.final_status;
}
function latestRecords(records) {
  const grouped = new Map();
  records.forEach((record) => {
    const current = grouped.get(record.record_id);
    if (!current || record.record_version > current.record_version) grouped.set(record.record_id, record);
  });
  return [...grouped.values()].sort((a,b) => b.record_version - a.record_version);
}
function renderTrace(snapshot) {
  const records = latestRecords(snapshot.recent_records).slice(0, 10);
  if (!records.length) { $("traceList").innerHTML = `<div class="change-summary empty">No TRACE records yet.</div>`; return; }
  $("traceList").innerHTML = records.map((record) => {
    const decision = lastDecision(record), cls = decision === "clear" ? "clear" : decision === "qualify" ? "qualify" : decision === "block" || record.final_status === "reject" ? "block" : "hold";
    const planName = record.metadata?.plan_name || record.metadata?.plan_id || record.record_id;
    const revision = record.metadata?.semantic_revision_of ? `<span class="trace-revision">revised from v${record.metadata.semantic_revision_of.record_version}</span>` : "initial version";
    return `<div class="trace-card ${cls}" data-record="${record.record_id}">
      <div class="trace-head"><span>${escapeHtml(planName)}</span><span>${escapeHtml(decision).toUpperCase()}</span></div>
      <div class="trace-claim">${escapeHtml(record.claim.text)}</div>
      <div class="trace-meta">v${record.record_version} · ${revision} · failed gates: ${escapeHtml((record.failed_gates || []).join(", ") || "none")}</div>
    </div>`;
  }).join("");
  document.querySelectorAll(".trace-card").forEach((card) => {
    card.onclick = () => {
      const record = snapshot.recent_records.filter((item) => item.record_id === card.dataset.record).sort((a,b) => b.record_version - a.record_version)[0];
      $("objectInspector").textContent = JSON.stringify(record, null, 2);
      document.querySelector(".inspector-details").open = true;
    };
  });
}

function describeEvent(event) {
  const p = event.payload || {}, type = event.event_type;
  if (type === "EMERGENCY_CALL") return `${p.merged ? "updated" : "new"} call: ${p.people} waiting at ${p.location_label}`;
  if (type === "INCIDENT_MERGED") return `${p.people_added || p.people || 0} additional people merged into ${p.group_id}`;
  if (type === "REASONING_STARTED") return p.cycle?.trigger_label || "reasoning cycle started";
  if (type === "REASONING_STEP") return p.step?.summary || p.step?.title;
  if (type === "REASONING_COMPLETED") return p.decision_change || "reasoning complete";
  if (type === "TRACE_WRITTEN") return `${p.plan_name || p.plan_id}: ${String(p.decision).toUpperCase()}`;
  if (type === "COMMITMENT_DECISION") return `${p.plan_name || p.plan_id}: ${p.decision}`;
  if (type === "ACTION_STARTED") return `${p.asset_id} · ${p.navigation_summary || p.action_type}`;
  if (type === "ACTION_INTERRUPTED") return `${p.asset_id} stopped: ${p.reason}`;
  if (type === "BOARDING_STARTED") return `${p.asset_id} boarding ${p.people} at ${p.group_id}`;
  if (type === "PEOPLE_PICKED_UP") return `${p.asset_id} picked up ${p.people}; evacuation route now requires TRACE clearance`;
  if (type === "UNLOADING_STARTED") return `${p.asset_id} unloading ${p.people} at the safe transfer dock`;
  if (type === "PEOPLE_DELIVERED") return `${p.people} delivered to safety; boat enters standby`;
  if (type === "ASSET_STANDBY") return `${p.asset_id} available at safe location`;
  if (type === "INCIDENT_CANCELLED") return `${p.group_id} cancelled`;
  if (type === "OBSERVATION") return `${p.source} reports ${p.route_id} ${p.reported_status}`;
  if (type === "INJECT_SHOCK") return `${p.shock_type} · ${p.target || "global"}`;
  if (type === "OUTCOME") {
    if (p.reason === "pickup_completed") return `${p.people_picked_up || 0} onboard; not yet counted rescued`;
    return `${p.reason}; delivered ${p.rescued_people || 0}`;
  }
  if (type === "ROUTE_STATUS_CHANGED") return `${p.route_id} is ${p.open ? "open" : "closed"}`;
  if (type.startsWith("SET_")) return Object.entries(p).map(([k,v]) => `${k}=${v}`).join(", ");
  return Object.keys(p).length ? JSON.stringify(p) : event.source;
}
function renderTimeline(events) {
  const rows = [...events].slice(-80).reverse();
  $("timeline").innerHTML = rows.map((event) => `<div class="timeline-row"><span class="t">${Number(event.simulation_time).toFixed(1)} s</span><span class="type">${escapeHtml(event.event_type)}</span><span class="desc">${escapeHtml(describeEvent(event))}</span></div>`).join("");
}

function stat(label, val) { return `<div class="stat"><div class="value">${val}</div><div class="label">${label}</div></div>`; }
function renderStats(metrics, snapshot) {
  const groups = Object.values(snapshot.truth.groups);
  const waitingPeople = groups.reduce((sum, group) => sum + Number(group.people_waiting || 0), 0);
  const pendingGroups = groups.filter((group) => !group.cancelled && !group.rescued && Number(group.people_waiting || 0) > 0).length;
  const onboard = Object.values(snapshot.truth.assets).reduce((sum, asset) => sum + Number(asset.passenger_count || 0), 0);
  const movingAssets = Object.values(snapshot.truth.assets).filter((asset) => asset.status === "moving").length;
  $("statsGrid").innerHTML = [
    stat("Waiting people", waitingPeople),
    stat("Onboard", onboard),
    stat("Delivered", metrics.rescued_people),
    stat("Active incidents", pendingGroups),
    stat("Moving assets", movingAssets),
    stat("TRACE lineages", latestRecords(snapshot.recent_records).length),
    stat("Clear / hold", `${metrics.clears} / ${metrics.holds}`),
    stat("Revisions", metrics.revisions),
  ].join("");
}

function addHistory(snapshot) {
  const time = Number(snapshot.truth.simulation_time), last = appState.history.at(-1);
  if (last && Math.abs(last.time - time) < .05) return;
  appState.history.push({
    time,
    water: Number(snapshot.metrics.max_water_depth || 0),
    rescued: Number(snapshot.metrics.rescued_people || 0),
    onboard: Object.values(snapshot.truth.assets).reduce((sum, asset) => sum + Number(asset.passenger_count || 0), 0),
    pending: Object.values(snapshot.truth.groups).reduce((sum, group) => sum + Number(group.people_waiting || 0), 0),
    support: Number(snapshot.metrics.last_model_support || 0),
    ood: Number(snapshot.metrics.last_ood_score || 0),
  });
  if (appState.history.length > 400) appState.history.shift();
}
function renderChart() {
  const canvas = $("metricChart"), dpr = window.devicePixelRatio || 1, rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(600, rect.width * dpr); canvas.height = 150 * dpr;
  const ctx = canvas.getContext("2d"); ctx.setTransform(dpr,0,0,dpr,0,0);
  const width = canvas.width / dpr, height = canvas.height / dpr;
  ctx.clearRect(0,0,width,height); ctx.fillStyle = "#fff"; ctx.fillRect(0,0,width,height);
  ctx.strokeStyle = "#e2e8ed"; for (let i=1;i<4;i++){const y=10+i*32;ctx.beginPath();ctx.moveTo(42,y);ctx.lineTo(width-12,y);ctx.stroke();}
  const h = appState.history; if (h.length < 2){ctx.fillStyle="#66798a";ctx.fillText("Run the simulation to populate metrics.",50,30);return;}
  const minT=h[0].time,maxT=Math.max(minT+1,h.at(-1).time),maxPeople=Math.max(1,...h.map(x=>x.pending),...h.map(x=>x.rescued));
  const x=(t)=>42+((t-minT)/(maxT-minT))*(width-56);
  const draw=(key,color,max)=>{ctx.strokeStyle=color;ctx.lineWidth=2;ctx.beginPath();h.forEach((row,i)=>{const px=x(row.time),py=height-20-(row[key]/max)*(height-40);i?ctx.lineTo(px,py):ctx.moveTo(px,py)});ctx.stroke();};
  draw("water","#1668b2",Math.max(1,...h.map(x=>x.water))); draw("pending","#e98b26",maxPeople); draw("onboard","#2f80c5",maxPeople); draw("rescued","#14865f",maxPeople); draw("support","#7251b5",1); draw("ood","#bd3434",1);
  [["water","#1668b2"],["waiting","#e98b26"],["onboard","#2f80c5"],["delivered","#14865f"],["support","#7251b5"],["OOD","#bd3434"]].forEach(([label,color],i)=>{ctx.fillStyle=color;ctx.font="10px system-ui";ctx.fillText(label,48+i*66,12)});
}

function escapeHtml(text) { return String(text ?? "").replace(/[&<>'"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c])); }
window.addEventListener("DOMContentLoaded", () => {
  initializeOperationalMap();
  setupControls();
  connectWebSocket();
});
