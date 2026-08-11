# WF-DFLD-01-REFERENCE Scientific Protocol Draft

## Document control

| Field | Value |
|---|---|
| Scenario | `WF-DFLD-01-REFERENCE` |
| Document version | `reference-protocol-draft-v1` |
| Status | **Design draft; not preregistered; not approved for confirmatory execution** |
| Date | 2026-08-10 |
| Intended implementation branch | A new branch created from the delivered Small release; never `demo-delta-scenario` itself |
| Scientific role | Medium/Reference integration target after Tasks 1 and 2 |
| Primary evaluation window | `[T0, T+96 h)`, with scenario censoring at `T+96 h` |
| State-estimation burn-in | `[T-48 h, T0)` |
| Canonical axes | `sigma=1.0`, `kappa=1.0`, `mu=1.0`, `iota=0.7`, `phi=4`, `pi=0.7`, `epsilon=reference-exposure-v1`, `delta=0.2` |
| Canonical onset | `predawn_weekend` |
| Expected observed volume | Approximately 2,900 controller-visible reports during `T0..T+96`, as a synthetic process-design target rather than an exact per-seed quota |
| Central physical event | One scripted, reduced-order Andrus levee breach at `T+52 h` in the canonical Reference setting |

This document is a protocol proposal. It records design decisions before implementation and is intentionally stricter about claims than the 2026-08-03 scenario sketch. It does not retroactively alter the delivered Small simulator, its configurations, its source, its registered studies, or its book/reference artifacts.

The terms **must**, **shall**, and **acceptance gate** describe requirements proposed for the frozen Reference protocol. The terms **default**, **provisional**, and **to freeze** identify decisions that may be revised during design review but only before validation and confirmatory seeds are materialized.

## Executive decision summary

- Reference remains the Flood-SAR Task 3 integration scenario; it is not the separate, broader public-demo domain discussed in the meeting.
- Implement it on a new branch and preserve every delivered Small scientific artifact byte-for-byte.
- Generate a 48-hour state-estimation burn-in followed by a half-open 96-hour evaluation window with one registered synthetic breach at `T+52 h`.
- Use offline simulation-grade geography curated from authoritative government sources, while treating the physical, exposure, and operational mechanisms as explicitly synthetic or reduced-order unless a field has direct provenance.
- Generate latent truth before a lossy zero/one/many observation channel; approximately 2,900 reports and a 95/hour expected peak are ensemble process targets, never forced per seed.
- Model the full `kappa=1.0` roster, T0-T4 aid tiers, crew/duty constraints, four logical authorities, route degradation, and strict one-resource/one-incident concurrency without claiming real emergency availability or command practice.
- Exercise full TRACE commitments, outcomes, restart, reconciliation, compensation, and failed compensation. Keep the transparent Toy predictor canonical; learned predictors remain unqualified without exact evidence.
- LEAP is an optional, separately governed post-admissibility study. Base Reference must validate first.
- Treat the sketch's approximately 4:1 load as an internally inconsistent historical design expectation, not a pass gate. Freeze metrics and publish adverse results without retuning.
- Separate development, selection, one-time validation, and remote confirmatory evidence; no confirmatory seed may be run locally.

### Terminology

- **Small / Reference / Demonstration:** the six-hour two-island scenario, the 96-hour eight-island integration scenario in this protocol, and the separately scoped 168-hour 14-island setting, respectively.
- **Flood-SAR:** the synthetic flood search-and-rescue scenario family.
- **TRW:** the project’s two-prong consistency contract: preventive synchronization/revalidation plus corrective recovery/compensation.
- **TRACE:** the typed claim, policy, commitment, and append-only audit runtime used to enforce and reconstruct that contract.
- **LEAP:** the optional budgeted-lookahead/admission-control layer; it allocates computation among already admissible options but does not observe or authorize the physical world.
- **Ground truth / public evidence:** hidden simulated world state used only for offline scoring, versus the lossy controller-visible reports, telemetry, receipts, and coordination deliveries available online.
- **Common random numbers (CRN):** stable keyed draws shared across controlled variants so an axis or policy change does not silently change the exogenous random realization.
- **HOLD / BLOCK / ESCALATE:** TRACE dispositions that withhold authorization, prohibit the action, or require a higher-authority/manual path.
- **UAS:** uncrewed aircraft system. **M2:** the principal lunar semidiurnal tide constituent. **OCI image:** a digest-pinned Open Container Initiative execution image. **NPZ:** a NumPy zipped-array artifact.
- **DWR / CDEC / USGS / 3DHP / NHD / DBW / OSM:** California Department of Water Resources; California Data Exchange Center; U.S. Geological Survey; 3D Hydrography Program; National Hydrography Dataset; California Division of Boating and Waterways; and OpenStreetMap.
- **EMAC / USCG:** Emergency Management Assistance Compact and U.S. Coast Guard. Their appearance in a synthetic tier does not assert legal activation or availability.
- **GIS / CRS / WGS84 / NAD83 / UTM / EPSG:** geographic information system; coordinate reference system; World Geodetic System 1984; North American Datum 1983; Universal Transverse Mercator; and the registry identifier used to name a CRS. **SR:** California State Route.
- **MLP / V-JEPA:** a multilayer perceptron predictor and a visual Joint-Embedding Predictive Architecture encoder-backed adapter, respectively.
- **Censoring:** the scenario ends before the eventual outcome is observed; active service is retained as active at `T+96`, not relabelled completed or failed. **F1:** the harmonic mean of precision and recall.

## 1. Purpose and research role

WF-DFLD-01-REFERENCE is the first full integration workload for the two-prong TRW consistency contract:

1. preventive synchronization and revalidation over a drifting predictive view; and
2. dependency-scoped recovery and compensation after a late observation invalidates an authorized commitment.

Reference is not a new public-demo domain. It remains Flood-SAR and extends the same scenario family as Small. Its purpose is to exercise mechanisms intentionally absent from Small: a breach, multi-day state evolution, multi-tier resource mobilization, crew duty cycles, multiple logical authorities, severe observation loss and delay, identity disputes, runtime restart, reordered evidence, incomplete outcomes, and failed compensation.

Reference is also not the 14-island Demonstration setting. Federation between two coordinating runtimes contending for one asset remains a separate research item.

### 1.1 Intended claims

If implemented and evaluated as specified, Reference may support claims that:

- the same versioned scenario family scales from Small to a materially more complex workload without changing its causal generation order;
- controller-visible evidence, TRACE records, commitments, outcomes, revisions, and compensation can be replayed exactly under multi-day load;
- ground-truth-first generation enables coverage, reconciliation, stale-execution, and recovery estimands that direct call authoring cannot support;
- the preventive and corrective halves of TRW can be exercised together under declared faults and partial outcomes;
- predictor substitution and revalidation are governed through one interface and fail closed for unqualified learned predictors;
- the system exposes a measured cost-consistency-coverage tradeoff rather than claiming that one policy dominates by construction.

Reference alone shall not support claims of:

- operational readiness for emergency response;
- hydrodynamic forecast accuracy;
- reproduction of the 1972, 1980, 1997, 2004, or 2022-2023 events;
- current staffing, dispatch, mutual-aid, bridge, ferry, gauge-threshold, or evacuation practice;
- demographic representativeness;
- casualty, injury, clinical, or mortality prediction;
- learned V-JEPA or MLP effectiveness in the Delta;
- universal benefit of adaptive refresh, compensation, or LEAP;
- legal authority, incident-command, or interagency behavior in an actual emergency;
- support for the 14-island Demonstration or federated-runtime claims.

## 2. Inherited requirements and immutable Small boundary

### 2.1 Requirements stated by Dr. Chang

The following are treated as inherited requirements rather than autonomous design choices:

- Reference follows Tasks 1 and 2 and is explicitly post-August-20 work.
- Canonical scale: eight islands, four communities, 96 evaluation hours, one breach, approximately 2,900 calls, four logical authorities, and an intended high-load regime around the breach.
- Canonical axes: `sigma=1.0`, `kappa=1.0`, `mu=1.0`, `iota=0.7`, `phi=4`, `pi=0.7`, and `delta=0.2`; onset is pre-dawn on a weekend.
- The generator order remains geography, meteorology, hydrology/breach, ground truth, observations, and resources, with later controller-only coordination/prior artifacts permitted after observations and resources.
- Ground truth must precede observations.
- Axes must be independently controllable.
- Reference needs the breach model and mutual-aid tiers.
- The physical-loop integration target includes reordered observations, authenticated false reports, identity disputes, crash/restart, silent provider success, partial and contradictory outcomes, and failed compensation.
- Reference is the integration-test target; the larger Demonstration remains distinct.

### 2.2 Small preservation invariant

The delivered Small implementation is immutable evidence.

- Do not modify or rewrite the `demo-delta-scenario` branch.
- Create Reference on a new branch from the final delivered Small commit.
- Do not change any Small source, configuration, seed list, validation report, figure, bundle, manifest, or result table in place.
- Shared refactors are permitted only if compatibility tests prove every committed Small scientific and public artifact byte-identical. If byte identity cannot be preserved, copy or version the Reference implementation rather than migrating Small.
- Reference data, source manifests, protocol versions, random namespaces, result directories, and CLI commands must be distinct.
- No Reference development result may be presented as a replication or extension of a Small registered result.

### 2.3 Source basis and precedence

This draft is grounded in `DELTA_SCENARIO_SPEC.md`, `TRW-JEPA-context.md`, the project correspondence record, the 2026-08-04 meeting transcript, and the delivered Small implementation. Those sources serve different roles:

1. a direct, later clarification from Dr. Chang controls an earlier sketch;
2. the committed Small artifacts control claims about what Small actually implements;
3. `DELTA_SCENARIO_SPEC.md` supplies the Reference design targets but not unverified real-world facts;
4. the meeting transcript supplies strategic scope—finish Flood-SAR for the paper/book, keep the broader public-demo domain separate, and treat LEAP as a cost-versus-consistency layer—not exact physical parameters;
5. current primary government sources control geography and operational metadata fields, subject to explicit retrieval dates and limitations.

The transcript is a conversational record and may contain transcription errors. Neither it nor an LLM-generated planning document is treated as an authoritative source for a station threshold, inventory, travel time, legal authority, historical event, or hydraulic coefficient. Any material conflict is preserved in the ambiguity ledger rather than silently harmonized.

## 3. Ambiguity ledger and proposed defaults

These defaults are selected for scientific defensibility and implementation clarity. Each must be reviewed before the protocol is frozen.

| ID | Ambiguity | Proposed default | Rationale and boundary |
|---|---|---|---|
| A1 | Does the stated 96-hour duration include the `T-48..T0` weather history? | No. Generate a 48-hour burn-in plus a 96-hour primary evaluation. | The original phase table needs pre-event state, while the scaling table names a 96-hour Reference. Separating burn-in prevents cold-start artifacts and makes the inferential window explicit. |
| A2 | Does approximately 2,900 calls include burn-in? | No. It is the expected controller-visible count in `T0..T+96`; burn-in reports are separate initialization evidence. | The original rate table and total do not reconcile uniquely. This default yields one auditable denominator and avoids forcing a count. |
| A3 | Are calls generated directly from a nonhomogeneous Poisson schedule? | No. Generate latent incidents from hazard, exposure, and vulnerability, then pass them through a zero/one/many observation channel. The phase curve calibrates expected observed volume only. | Direct call generation would violate the ground-truth-first rule and destroy coverage and reconciliation estimands. |
| A4 | Is the canonical breach stochastic? | No. At `sigma=1.0`, Reference contains one registered scripted breach at `T+52`. Parameter sweeps may alter physical consequences through a versioned severity response, but the canonical event identity remains fixed. | A fixed central event makes policy comparisons share the same causal challenge. No claim is made that the time or geometry forecasts a real breach. |
| A5 | Is breach inflow a calibrated hydrodynamic model? | No. Use a reduced-order signed stage-difference/mass-balance model with exposed coefficients and uncertainty limits. | This supports causal simulation and audit, not forecasting. |
| A6 | What does `phi=4` mean? | Four logical evidence/coordination authorities, with agency and reclamation-district sources routed through them. They are simulation roles, not representations of legal incident command. | The source specification names more than four real entities but fixes `phi=4`; grouping must therefore be explicit. |
| A7 | Which four logical authorities? | Provisional: Sacramento operational-area dispatch; Delta reclamation/flood-fight coordination; state flood/access coordination; regional water/air rescue coordination. | These roles isolate information ownership and delay without asserting actual command relationships. Names and routing must be reviewed against source data before freeze. |
| A8 | Does `kappa=1.0` mean inventory only or successful aid delivery? | Inventory and eligible tier rosters only. Activation, travel, staging, crew, road, weather, and authority delays remain separate. | Otherwise `kappa`, `mu`, `delta`, `phi`, and physical access would be confounded. |
| A9 | Is the approximately 4:1 ratio an acceptance gate, and at which `kappa`? | No numerical pass/fail gate. The source sketch is internally inconsistent: its capacity section associates approximately 4:1 with `sigma=1.0, kappa=0.5`, while its scaling table and Reference YAML associate approximately 4:1 with canonical `kappa=1.0`. Preserve that discrepancy in protocol history, treat approximately 4:1 only as an inherited development expectation, and report every frozen load definition and unserviceable-window count. | Small showed that ambiguous capacity definitions can create misleading ratios. Reference shall not select a definition or retune inventory after validation or holdout inspection. |
| A10 | Which demand/capacity metric is primary? | Strict one-resource/one-active-incident capability-and-route matching, with explicit unserviceable states. Report uncapped service-unit and historical normalized sensitivity measures separately. | This is operationally interpretable and prevents one physical asset from covering multiple concurrent incidents. |
| A11 | Are gauge thresholds copied from the 2026-08-03 sketch? | No. A gauge is threshold-operative only if the frozen authoritative source supplies the threshold and its semantics. Missing values remain unavailable and non-operative. | Station identities and thresholds change; synthetic stages are not CDEC forecasts. |
| A12 | Is MRU “Middle River at Union Point”? | No. Use the verified current station identity in the source registry; the prior Small audit identified MRU as Middle River at Undine Road. | Never preserve a known metadata error for narrative continuity. |
| A13 | Is the 1,400-person roster demographic reconstruction? | No. It is a deterministic synthetic teaching cohort placed within simulation-grade source geography. | No real addresses or claims of representative demographics. |
| A14 | Are real phone numbers, names, languages, or authentication keys used? | No. Use synthetic display tokens, controlled vocabularies, and project-owned test keys. | Prevent personal data and secret leakage. |
| A15 | Does an authenticated report imply that its content is true? | No. Authentication establishes simulated source identity/integrity only; content may be wrong, stale, benign, or adversarially false. | This distinction is necessary to test false but authenticated evidence. |
| A16 | Are runtime faults mixed into every baseline run? | Use two registered workload profiles: nominal Reference and faulted Reference. The faulted profile is mandatory for integration acceptance; policy efficacy comparisons must state which profile is the estimand. | This separates ordinary performance from recovery behavior while exercising every required fault. |
| A17 | Is LEAP required for core Reference completion? | No. Provide an optional, auditable post-admissibility interface. Freeze and validate base TRW Reference before any LEAP efficacy study. | This avoids confounding the Reference simulator with a new metareasoning method. |
| A18 | May LEAP or a simulator satisfy a freshness requirement? | No. Simulated lookahead is computation, not observation. Only a declared physical/evidence channel can refresh a claim. | TRW authorization remains authoritative. |
| A19 | Which predictor is canonical? | The transparent qualified Toy predictor. MLP and V-JEPA remain unqualified unless an exact, separately frozen qualification artifact covers the action class. | Reference tests accountability and substitution, not learned flood accuracy. |
| A20 | How is confirmatory work executed? | A dedicated immutable remote workflow after preregistration; no local confirmatory access. | Preserves the development/confirmation boundary established in Small. |
| A21 | What exactly does the stated peak of 95 calls/hour mean? | The maximum of the *expected* counts over a fixed, protocol-declared set of one-hour bins in `T0..T+96`, not the realized maximum in an individual seed and not the mean across the entire 12-hour breach phase. Freeze the expected peak bin from the analytical intensity model before validation. | Expected intensity, realized maximum, and phase mean are different estimands. Conflating them would bias calibration and acceptance. |
| A22 | Do the ten Reference crossings have to be the first ten catalog IDs even though several are exterior connectors for islands outside the eight-island exposure set? | Retain `XNG-01..XNG-10` as the access network specified in the sketch, including the minimum exterior network footprint needed to connect them. Do not generate Reference cohort exposure outside `ISL-01..ISL-08`. Label exterior crossings as boundary connectors rather than evidence that their associated islands are in the Reference exposure set. | A routing network may legitimately include boundary connectors, but extent and exposure must not be silently expanded. |
| A23 | How does continuous `kappa` scale discrete assets? | Define the `kappa=1.0` roster first. Assign each base/class asset a frozen inclusion rank and threshold, so inventories are nested and deterministic as `kappa` changes. Do not fractionally instantiate an asset, round separately per evaluated seed, or guarantee a minimum capability solely to improve outcomes. | This preserves inventory-only semantics, monotonicity, and common random numbers without inventing fractional physical resources. |
| A24 | What wall-clock instant anchors `T0`? | Provisional: Saturday 2026-01-17 at 04:00:00 Pacific Standard Time (`2026-01-17T04:00:00-08:00`), with timezone and UTC offset both stored. Treat it as a synthetic clock anchor, not the date of a historical event. | “Pre-dawn weekend” is otherwise insufficient for deterministic tide phase, staffing, daylight, and timezone behavior. This interval avoids a daylight-saving transition. |
| A25 | Are phase endpoints inclusive? | Use half-open intervals throughout: burn-in is `[T-48,T0)`, primary evaluation is `[T0,T+96)`, and `T+96` is the censoring instant. An event at exactly `T+96` is post-window evidence unless a schema explicitly identifies it as the censoring observation. | This prevents double counting at phase boundaries and makes the 96-hour denominator exact. |
| A26 | What are the simulator and capacity evaluation grids? | Provisional: 300-second physical output, 60-second decision opportunities, and 900-second registered capacity evaluation. Events retain exact integer simulation timestamps between grids. Freeze these values after development profiling and before validation; do not change them to improve a policy result. | These are autonomous numerical-analysis defaults, not values supplied by a historical source. Separate grids control artifact size while retaining decision and capacity semantics. |

## 4. Scenario contract

### 4.1 Version namespace

The first implementation should reserve, but not claim as frozen until review, the following identifiers:

```text
trace-delta-reference-scenario-v1
delta-reference-generator-v1
delta-reference-geography-v1
delta-reference-physical-v1
delta-reference-breach-v1
delta-reference-ground-truth-v1
delta-reference-observations-v1
delta-reference-resources-v1
delta-reference-governance-v1
delta-reference-faults-v1
delta-reference-recovery-v1
delta-reference-acceptance-v1
delta-reference-validation-v1
delta-reference-replay-manifest-v1
```

Reference must use a new keyed-randomness namespace and must never share Small stage names where sharing could accidentally preserve or perturb Small draws.

### 4.2 Canonical parameter set

```yaml
scenario_id: WF-DFLD-01-REFERENCE
scenario_schema_version: trace-delta-reference-scenario-v1
generator_version: delta-reference-generator-v1

timeline:
  onset_clock: predawn_weekend
  evaluation_start_iso8601: "2026-01-17T04:00:00-08:00"
  timezone: America/Los_Angeles
  burn_in_start_s: -172800
  evaluation_start_s: 0
  evaluation_end_s: 345600
  output_tick_s: 300
  decision_tick_s: 60
  capacity_evaluation_tick_s: 900

axes:
  sigma: 1.0
  kappa: 1.0
  mu: 1.0
  iota: 0.7
  phi: 4
  pi: 0.7
  epsilon_profile: reference-exposure-v1
  delta: 0.2

extent:
  islands: [ISL-01, ISL-02, ISL-03, ISL-04, ISL-05, ISL-06, ISL-07, ISL-08]
  communities: [TWN-01, TWN-02, TWN-03, TWN-04]
  crossings: [XNG-01, XNG-02, XNG-03, XNG-04, XNG-05, XNG-06, XNG-07, XNG-08, XNG-09, XNG-10]
  synthetic_people: 1400
  scripted_breaches: 1

process_targets:
  expected_public_reports_evaluation: 2900
  expected_peak_public_reports_per_hour: 95
  breach_time_s: 187200
  intended_peak_load_regime: approximately_4_to_1_development_target_only

canonical_predictor:
  implementation: toy
  qualification: exact_teaching_fixture_only

fault_profiles:
  baseline: reference-nominal-v1
  integration_acceptance: reference-faulted-v1
```

The eventual YAML shall contain fully expanded profile identifiers and hashes rather than relying on implicit defaults. The identifier crosswalk is:

- islands: Andrus, Brannan, Twitchell, Sherman, Tyler, Grand, Staten, and Bouldin (`ISL-01..ISL-08`);
- communities: Isleton, Walnut Grove, Locke, and Ryde (`TWN-01..TWN-04`);
- crossings: Rio Vista, Antioch, Threemile Slough, Isleton, Walnut Grove, Paintersville, Bethel Island, Real McCoy Ferry, J-Mack Ferry, and Woodward Island Ferry (`XNG-01..XNG-10`).

The source registry, rather than this narrative crosswalk, is authoritative for current spelling, geometry, facility status, and metadata. Per A22, a crossing may be a boundary connector without expanding the eight-island exposure set.

### 4.3 Generation and execution order

The declared order shall match execution:

1. static geography, facilities, governance source registry, and local coordinate frame;
2. meteorology from `sigma` and onset category;
3. hydrology, levee state, breach state, inundation/access state, and crossing state;
4. synthetic exposure, trajectories, occupancy, infrastructure truth, latent incidents, and candidate audit;
5. lossy public observations from truth using `iota`;
6. hidden resource/crew state and separate controller-visible telemetry from `kappa`, `mu`, and `delta`;
7. controller-visible coordination delivery using `phi`;
8. predictor prior/calibration profile from `pi`;
9. optional registered fault schedule;
10. TRACE mission execution and recovery;
11. offline evaluation against hidden truth.

No controller or predictor may read hidden artifacts from steps 4 or 11. It may consume only the controller-visible reports, resource/crew telemetry, coordination deliveries, and prior/profile inputs emitted by steps 5 through 8.

## 5. Offline simulation-grade geography

### 5.1 Source hierarchy

Runtime and CI must be network-free. An offline builder shall create a clipped Reference bundle using the following source precedence:

1. county or reclamation-district government GIS for island/tract operational footprints and district associations;
2. California DWR levee, Local Maintenance Area, and Delta data as state-level cross-checks;
3. current Census TIGER/Line place geometry for administrative community boundaries;
4. Caltrans bridge inventory and state-highway network for crossings and SR-12/SR-160 topology;
5. USGS 3DHP/NHD hydrography for the clipped waterway network;
6. DWR Bay-Delta DEM v4.3, or a versioned successor explicitly approved before freeze, for clipped elevation summaries;
7. CDEC station metadata for gauge identity and threshold availability;
8. official city, county, State Parks/DBW, fire, airport, hospital, and facility records for the minimal operational fixture;
9. OSM only as a secondary geocoding or topology aid, never as an unlabelled replacement for an authoritative operational field.

The project shall describe the result as **offline simulation-grade geography curated from authoritative government sources**, not authoritative or survey-grade geography.

### 5.2 Data products

The bundle shall include:

- eight island/tract polygons and source crosswalks;
- four community polygons or points, with administrative versus simulated exposure boundaries distinguished;
- ten crossing points and their connected road/water edges;
- clipped road and waterway topology sufficient for deterministic routing;
- levee segments with district/source associations;
- gauges with station identity and threshold status;
- resource bases, hospitals, shelters, ramps, airports, fuel/staging points, and non-operative approximate facilities where necessary;
- governance source entities and their mapping to four simulated logical authorities;
- elevation summary cells or derived fixed-point summaries, not unrestricted upstream rasters when redistribution is not permitted.

Source geometry shall be stored in WGS84. The proposed metric working CRS is NAD83 / UTM Zone 10N (`EPSG:26910`), selected from the current Small geography design; the Reference builder shall verify its area of use and datum against every input before freeze. Runtime coordinates shall be quantized fixed-point integers. Round-trip tolerances and quantization shall be frozen.

### 5.3 Provenance and licensing

Every source entry shall record:

- stable source identifier;
- agency and dataset title;
- landing-page URL and machine-readable retrieval URL separately;
- retrieval timestamp;
- license/redistribution status;
- source CRS, datum, vertical datum where applicable, units, and nodata handling;
- archive digest and exact extracted-member digest;
- query, clip, repair, transformation, and quantization versions;
- output feature IDs and source-feature crosswalk;
- field-level source tier and whether a value is operative or contextual.

If redistribution is unclear, commit only the locator, digest, retrieval procedure, transformation code, and a license-compatible derived fixture.

### 5.4 Geography QA

Acceptance tests shall verify:

- valid and nonempty geometries;
- documented geometry repairs and area change;
- expected region bounds;
- point-in-polygon placement;
- crossing proximity to both connected networks;
- complete route connectivity or an explicitly declared disconnection;
- levee-to-island and district referential integrity;
- facility/source referential integrity;
- CRS round trips and fixed-point determinism;
- no real residential addresses;
- no network access at runtime;
- safe refresh behavior for HTML responses, malformed archives, traversal, symlinks, oversized files, and digest mismatch.

Specification acres, elevations, and historical narrative values shall be retained as contextual scenario fields alongside source-derived summaries. One shall never silently replace the other.

## 6. Timeline and state-estimation burn-in

Per A25, every phase interval in this section is start-inclusive and end-exclusive. State may be sampled at the `T+96` censoring instant, but events occurring there are not counted as primary-window arrivals or completions.

### 6.1 Burn-in: `T-48..T0`

Burn-in is generated, replayed, and available to the controller as permitted evidence, but excluded from the primary 96-hour outcome denominator.

It serves four purposes:

- initialize hydrologic and meteorological lag states without a cold start;
- establish prior claims, observation ages, and predictor uncertainty at `T0`;
- permit forecast-based prepositioning and crew decisions;
- create a reproducible pre-event record against which later revisions can be audited.

Burn-in reports, mobilizations, costs, and commitments shall be reported separately. Any resource dispatched during burn-in may remain busy at `T0`; primary evaluation must inherit that state rather than reset it.

### 6.2 Primary evaluation: `T0..T+96`

The primary phases are:

| Phase | Window | Synthetic mechanism tested |
|---|---|---|
| R0 | `T0..T+12` | lull, repositioning, and post-burn-in evidence aging |
| R1 | `T+12..T+30` | second atmospheric-river pulse and external-release notice |
| R2 | `T+30..T+52` | high-stage stress and visible non-breach precursors |
| R3 | `T+52..T+64` | scripted breach, access loss, and report surge |
| R4 | `T+64..T+78` | tide/runoff stacking and sustained rescue load |
| R5 | `T+78..T+96` | clearing, systematic sweep, recovery, and censoring |

These R-phase labels and the `T+12` subdivision are proposed analytical partitions derived from the scenario sketch's lull, release-notice, breach, stacking, and clearing periods. They are not historical-event phases and shall be frozen before validation.

Any continuation after `T+96` is a separate recession extension and shall not be mixed into Reference’s primary estimand.

## 7. Reduced-order meteorology, hydrology, breach, and access

### 7.1 Modeling claim

The physical layer is a deterministic, reduced-order teaching and systems-test model. It is not a calibrated flood forecast or reconstruction. Real station identifiers, topology, and source summaries constrain the setting; generated stages, flows, inundation, and breach consequences remain synthetic.

### 7.2 Meteorology

Emit at each frozen tick:

- rain intensity and accumulated synthetic rainfall;
- wind speed/direction;
- ceiling/visibility state;
- UAS and rotary-wing operability states;
- pulse identifier and coefficient provenance.

`sigma` changes only meteorological/hydrologic severity and downstream causal truth. It shall not modify resources, authority partitions, observation-channel draws, or predictor identity.

The atmospheric-river pulse shapes from the original specification may be used as versioned scenario inputs, but “calibrated to” historical storms shall not appear unless a separate quantitative calibration report demonstrates the claim.

### 7.3 Hydrology

Gauge stage shall expose additive components separately:

```text
synthetic_stage = baseline_component
                + m2_tide_component
                + runoff_response_component
                + wind_setup_component
                + upstream_release_component
```

Requirements:

- The inherited M2 period is 12 h 25 min (44,700 s); phase and amplitude remain explicit source/protocol fields.
- Basin lags and coefficients are frozen and unit-checked.
- Release notices and physical release effects are separate events.
- Every gauge has a source-bound identity, sample time, units, and threshold status.
- Only source-supported thresholds may drive decisions.
- Generated values shall be labelled `synthetic_stage`, never CDEC observations or forecasts.
- Additive components, final value, and saturation/guard behavior shall be emitted for audit.

### 7.4 Levee and breach model

Levee truth shall include time-indexed condition, seepage/anomaly state, patrol state, evidence visibility, and district/source association.

The canonical Reference breach is:

- one scripted Andrus west-side segment event;
- onset at `T+52 h`;
- preceded by synthetic visible anomaly opportunities;
- breach-free before the registered onset;
- represented by a versioned width-growth curve and signed stage-difference inflow;
- incapable of being closed during the 96-hour evaluation;
- explicitly synthetic in timing, geometry, and hydraulic coefficients.

The reduced-order inundation model shall conserve declared volume within numerical tolerance, expose signed inflow/outflow, bound physically impossible states, and use fixed-point or carefully specified decimal arithmetic where practical.

Reference contains no cascade breach. A second breach remains Demonstration scope or a separately preregistered stress variant.

### 7.5 Access and travel

Road, bridge, ferry, water-route, and aviation states shall be time-indexed and consumed by all travel calculations.

- Crossing loss must arise from declared physical/operational state, not a controller-only label.
- A unit dispatched before a closure may be delayed, rerouted, stranded, or fail to arrive.
- Ferries have stage/wind/operational constraints only when sourced or explicitly synthetic.
- Travel time is recomputed at route entry and at declared checkpoints for extended commitments.
- The truth path and controller belief path are separate.
- No hard-coded “route open” evidence is permitted in predictor requests.

## 8. Synthetic exposure, truth, and incidents

### 8.1 Cohort and structures

Generate approximately 1,400 synthetic people with deterministic, non-identifying IDs. Place synthetic structures within verified simulation exposure extents using keyed spatial sampling and minimum separation. Do not use parcels or real residential addresses.

Each person may carry synthetic attributes needed by the scenario:

- household/structure membership;
- mobility class;
- medical dependency category;
- language-access category;
- access to transport;
- daytime/nighttime occupancy pattern;
- synthetic callback/contact tokens;
- deterministic change-point trajectory.

These fields are mechanisms, not demographic estimates. Aggregate composition shall be declared in an exposure profile and varied only through `epsilon`.

### 8.2 Truth state

At every simulation tick or recoverable change point, truth shall determine:

- person position and state;
- structure occupancy, flood, utility, and access state;
- road/crossing/ferry/air-operability state;
- levee condition and breach state;
- shelter and facility state;
- latent incident eligibility, onset, duration, service need, and resolution.

Resource and crew physical truth is generated in the separately ordered resource stage in Section 11, with controller-visible telemetry emitted as a distinct view. It is not silently folded into exposure truth or made directly available to the controller.

### 8.3 Latent incidents

Generate incidents from keyed structure/person/infrastructure episodes, not from a desired call count. Candidate probability may depend on:

```text
incident-type intercept
× local physical hazard
× occupancy or affected subject set
× synthetic vulnerability
× access/utility condition
```

Episode formation shall suppress repeated incidents while the same enabling state and subject set persist. Distinct simultaneous incident types may coexist. Emit a hidden candidate-audit artifact with probability, random-draw digest, episode key, disposition, and suppression reason.

Incident taxonomies may include stranded structure, vehicle rescue, levee inspection, medical access, welfare check, missing person, animal/livestock, information need, and infrastructure/hazard response. Information requests without a latent harmed person may arise from public-state uncertainty, but they still require an explicit truth-side event or question state.

## 9. Lossy observation and identity channel

### 9.1 Causal channel

The observation channel maps each latent incident to zero, one, or many reports. It shall separately model:

- non-reporting;
- initial reports;
- duplicates and multi-channel reports;
- delayed reports and out-of-order delivery;
- dropped calls and callback failure;
- location method and error;
- taxonomy and description disagreement;
- occupant-count conflict and later revision;
- third-party welfare checks;
- false/benign levee reports;
- authenticated but false content;
- language-access delay;
- identity disputes and later evidence-based reconciliation.

No public call may contain a truth incident ID, truth person ID, hidden lineage label, or unique descriptor derived from a hidden identifier.

### 9.2 Volume and phase calibration

At `iota=0.7`, fixed global coefficients shall target:

- approximately 2,900 controller-visible reports during `T0..T+96` in expectation;
- a phase-local expected maximum near 95 reports/hour during the declared breach surge;
- the frozen channel fractions and location-error distributions.

The process shall not force 2,900 reports in any seed, solve coefficients per seed, or tune the canonical illustrative seed. The breach phase target is an expectation, not a realized maximum gate.

Because the original phase table does not uniquely reconcile with the stated total, a calibration script shall fit non-peak phase multipliers on development seeds while holding the 95/hour breach target fixed. It shall record all candidate coefficients, objective values, convergence, and adverse residuals before validation seeds are materialized.

### 9.3 Public and hidden artifacts

Separate:

1. raw controller-visible reports;
2. authority-specific delivery and authentication envelopes;
3. controller-derived suspected/confirmed/rejected/superseded relationships;
4. hidden truth lineage and score labels;
5. offline evaluation results.

Deleting hidden lineage before runtime must produce byte-identical public decisions, TRACE records, commitments, and outcomes.

### 9.4 Authentication

Authentication shall use project-owned deterministic test keys or signed fixture tokens. It verifies source and envelope integrity only. Tests shall include:

- valid signature with false content;
- invalid signature with plausible content;
- replayed envelope;
- delayed valid envelope;
- source-key rotation;
- duplicate authenticated reports over different channels.

No production credentials or real callback data may enter the repository, logs, fixtures, figures, or artifacts.

## 10. Governance and coordination (`phi=4`)

### 10.1 Logical-authority model

The four authorities are simulation roles that own evidence queues, not a claim about legal command. Each has:

- source entities and jurisdiction tags;
- local evidence and belief state;
- delivery latency and uptime process;
- allowed action/verification request classes;
- authority version and simulated signing identity;
- deterministic evidence-sharing rules;
- TRACE-visible handoff and receipt events.

The provisional four-role mapping in A7 must be reviewed and frozen in a governance data card.

### 10.2 Coordination behavior

At `phi=4`:

- raw evidence initially enters its source authority;
- cross-authority sharing has deterministic, keyed latency and possible loss;
- reports may arrive in different orders at different authorities;
- identity/belief revisions propagate through append-only events;
- resource requests and approvals are explicit;
- no authority silently reads another authority’s private state;
- one canonical runtime may coordinate all four roles for Reference, provided role partitions remain explicit.

Federation between independently authoritative TRACE runtimes is not part of Reference. That remains Demonstration scope.

### 10.3 Axis isolation

Changing only `phi` may change delivery, visibility, authorization delay, duplicate work, and coordination records. It must not change physical hazard, latent truth, raw reports, inventory, crew health, or predictor identity.

## 11. Resources, mutual-aid tiers, crews, and capacity

### 11.1 Resource contract

Every physical resource shall declare:

- resource ID and class;
- capability set and normalized analytical service units;
- physical capacity where relevant;
- home base and current staged base;
- owning and requesting logical authorities;
- mutual-aid tier;
- activation, travel, staging, and turn-around components;
- crew roster, qualification, duty limit, rest requirement, and fatigue state;
- fuel/battery/consumable state;
- weather, depth, road, crossing, and daylight constraints;
- availability/degradation state;
- deterministic service-duration rule;
- one-physical-resource/one-active-commitment concurrency.

Hidden resource/crew truth and controller-visible telemetry shall be independently typed and checksummed. Online dispatch and predictor requests use telemetry, receipts, and visible coordination evidence—not hidden availability or fatigue state. Offline capacity/scoring may use hidden resource truth after runtime. Telemetry delay, omission, and contradiction are observation-quality descendants of `iota`; physical availability, fatigue, and degradation remain descendants of `delta`.

Resource quantities in the 2026-08-03 sketch are planning inputs, not verified current emergency inventories. Each fixture shall cite its source or be labelled a synthetic roster.

### 11.2 Mutual-aid tiers

Implement T0 through T4 as staged eligibility and arrival mechanisms:

- T0 local;
- T1 county;
- T2 regional;
- T3 state;
- T4 federal/EMAC-style external assistance.

Reference models request, approval, activation, staging, travel, and arrival. It does not claim to reproduce actual compact law or live availability. `kappa` controls inventory/roster scale only; `mu` controls activation, travel, and staging friction; `phi` controls coordination/approval information flow; `delta` controls initial outage, fatigue, and facility degradation.

The source sketch's provisional `kappa=1.0` planning roster spans Isleton/Walnut Grove, Rio Vista, Oakley/Brentwood, Antioch, Stockton, Sacramento, Travis AFB, and USCG Air Station San Francisco. Its candidate classes are rescue boats, airboats, high-water vehicles, Type I engines, rotary-wing rescue and reconnaissance aircraft, small UAS, ambulances, law-enforcement units, swiftwater teams, and levee flood-fight crews. These names and quantities are *scenario design inputs*, not claims about current inventories, staffing, response times, or availability. Before freeze, each base/class row must be either supported by an allowed source for the stated field or explicitly relabelled as a synthetic fixture. Discrete `kappa` scaling follows A23.

### 11.3 Crew model

Inventory without an eligible crew is not available capacity.

- Duty and rest are time-indexed.
- Crew swaps are explicit events.
- Fatigue changes availability/degradation, not hazard.
- A crew cannot operate two assets concurrently.
- Credential/capability matching is enforced.
- Service extending beyond `T+96` remains active at censoring and is not relabelled completed.

### 11.4 Capacity accounting

Primary strict capacity at each 15-minute evaluation point shall:

- use active unresolved truth incidents for offline demand;
- require capability and route compatibility;
- require scheduled, mobilized, reachable, crewed, and non-degraded resources;
- assign a physical resource to at most one incident;
- cover an incident only when service capacity is sufficient;
- maximize coverable incident units deterministically;
- return zero for zero demand;
- return an explicit unserviceable state for positive demand with zero compatible capacity.

Report at least:

- active demand units;
- strict matched capacity and finite strict load;
- strict unserviceable windows;
- uncapped compatible service-unit sensitivity;
- commitment-covered demand;
- residual demand and free strict capacity;
- residual pressure and residual unserviceable windows;
- inventory, crewed inventory, mobilized inventory, and arrived inventory separately.

The intended approximately 4:1 breach regime shall not be obtained by adding or removing resources after viewing validation or confirmatory results.

## 12. Fault, recovery, and compensation protocol

### 12.1 Workload profiles

Two profiles are required:

1. `reference-nominal-v1`: physical and observation uncertainty without injected runtime/provider faults;
2. `reference-faulted-v1`: the same exogenous world and reports plus a frozen, keyed fault schedule.

The profiles shall use common random numbers and byte-identical geography, meteorology, hydrology, truth, raw observation-channel output, and resource schedules. Only the registered fault-delivery overlay and runtime/provider behavior may differ. An injected authenticated-false envelope belongs to that overlay; it must not silently rewrite the common raw observation artifact.

### 12.2 Required fault families

The faulted profile must exercise:

- reordered evidence delivery;
- duplicated delivery/retry;
- authenticated false report;
- identity dispute and later visible revision;
- controller/runtime crash and restart;
- silent provider success after client timeout;
- partial success;
- contradictory outcome evidence;
- failed compensation;
- stale acknowledgement or source-key rotation;
- delayed completion arriving after scenario censoring.

Fault times and targets shall be selected through fixed keyed rules or a committed manifest before development comparison. Do not target a favorable commitment after observing a run.

When a fault requires an eligible runtime object, the protocol shall name a semantic trigger in advance—for example, the first compatible reversible commitment after a fixed phase boundary with a digest tie-break—rather than hard-code an object learned from an inspected run. A no-eligible-object result is reported as fault unreachability; development may repair the workload or trigger rule before validation, but the final rule and all failed attempts remain in the calibration record.

### 12.3 Runtime durability

The implementation shall use:

- append-only, hash-chained TRACE records;
- durable commitments with exact authorizing record/version;
- evidence ledger digests;
- idempotency keys for external/provider actions;
- durable outbox/inbox or equivalent exactly-once-effect discipline over at-least-once messages;
- provider receipts that can reconcile silent success;
- restart from persisted state without hidden in-memory authority;
- explicit timeout, retry, cancellation, and late-result semantics.

Crash/restart replay must reconstruct the same next controller decision from the same persisted prefix.

### 12.4 Outcomes

Outcomes shall distinguish:

- scheduled completion time;
- observed completion time;
- censoring time;
- completed within window;
- active at scenario censoring;
- failed before effect;
- partial effect;
- silent success later reconciled;
- contradicted outcome;
- duplicate provider attempt suppressed;
- unknown outcome at censoring.

Never truncate a completion time to the scenario horizon.

### 12.5 Compensation

Each reversible commitment declares:

- compensation action;
- preconditions;
- affected dependency set;
- idempotency key;
- expected repair endpoint;
- timeout and retry policy;
- possible partial/failure states.

Irreversible effects are not falsely labelled compensated. Failed or incomplete compensation creates an explicit residual consistency debt and escalation. Recovery shall be evaluated against hidden truth only after runtime; online affected-set construction may use controller-visible dependencies only.

## 13. TRACE, predictors, and optional LEAP

### 13.1 TRACE path

All durable action shall pass through:

1. controller-visible evidence construction;
2. predictor request and exact request digest;
3. typed claim;
4. policy and revalidation guard;
5. TRACE record and consumer action;
6. commitment citing the exact record/version;
7. outcome, revision, or compensation record.

No direct policy-engine shortcut is permitted for Reference execution.

### 13.2 Predictor provenance

Every learned or toy predictor shall report and bind:

- predictor version and model hash;
- calibration version and hash;
- encoder version/checkpoint hash when applicable;
- feature and action schema versions;
- training snapshot;
- qualified action classes;
- exact qualification artifact and evaluation-report hashes.

The Toy predictor is a transparent teaching fixture, not an empirical flood predictor. MLP and V-JEPA fail closed as `UNQUALIFIED` unless an exact qualification artifact covers the predictor/calibration/schema/action tuple. Optional real V-JEPA feature extraction remains offline and shall not be represented as a Delta predictor study.

`pi` selects a prior/calibration profile within a configured predictor. It never selects Toy versus MLP versus V-JEPA.

### 13.3 Predictor request context

Requests shall include only public/controller-visible state:

- candidate plan and grounded action;
- route/crossing belief and sample age;
- nearest registered gauge identity, synthetic stage sample, sample age, and threshold status;
- weather and operability state;
- compatible resource and crew telemetry;
- coordination latency;
- selected prior profile;
- optional content-addressed visual features;
- complete canonical request digest.

### 13.4 Optional LEAP interface

Reference shall expose a feature-gated, typed interface for a later LEAP study, but LEAP is not required for base Reference acceptance.

The recommended seam is after TRW constructs admissible verification/safe-alternative options and before a commitment is made. LEAP may allocate bounded counterfactual computation among ambiguous admissible options. It may not:

- bypass BLOCK/HOLD/ESCALATE;
- treat simulation as observation;
- read hidden truth;
- authorize an unqualified predictor;
- ignore deliberation latency;
- replace post-deliberation revalidation.

Base TRW, static ordinal selection, selective LEAP, all-option lookahead, and Pareto-screen lookahead must be separately identifiable policies. A LEAP efficacy study requires its own development and confirmatory protocol.

### 13.5 Core policy baselines and ablations

Base Reference shall be useful without LEAP. Its registered policy suite should include:

- no proactive refresh, with the same safety gate retained;
- fixed-interval refresh over a preregistered grid;
- validity-clock refresh;
- adaptive TRACE refresh using the paper's declared trigger families and channel-admissibility rule;
- prevention-only TRACE, with corrective recovery disabled, as a recovery ablation;
- adaptive TRACE with compensation enabled;
- an offline truth-aware upper bound used only to quantify headroom, never presented as deployable.

All deployable policies shall share exogenous worlds, candidate plans, predictor identity, channel menu, safety gate, fallback behavior, resource logic, and fault schedules. Policies may differ only in the declared refresh, selection, and recovery decisions. Verification latency and cost, HOLD/refusal delay, compute, and failed recovery work are charged to the policy that caused them. Cost-matched operating points are selected without confirmatory access.

### 13.6 Development-only LEAP iteration loop

If LEAP is pursued, freeze base Reference first and iterate only on spent LEAP-development seeds. Each iteration shall:

1. compare static ordinal selection, selective LEAP, all-option lookahead, and Pareto-screen lookahead on paired worlds;
2. record every trigger threshold, budget, simulator call, wall/simulated latency, cache hit, option evaluated, and post-deliberation revalidation result;
3. measure the joint frontier over physical verification cost, compute, consistency violations, eligible service, completion, and recovery debt;
4. reject any candidate that weakens TRW authorization, reads hidden truth, or obtains apparent benefit by omitting deliberation latency;
5. retain all candidate configurations and adverse results in a development registry.

Candidate selection then uses a separately frozen selection set, followed by a one-time validation gate. Only after that process may a distinct LEAP confirmatory protocol be written. This gives multiple viable integration strategies a fair local comparison; it does not assume in advance that one seam or budget allocator must win.

## 14. Axes and common random numbers

### 14.1 Causal semantics

| Axis | Source design range | Allowed causal effects | Forbidden direct effects |
|---|---:|---|---|
| `sigma` | `0.2..2.0` | meteorology, hydrology, breach consequences, access, and downstream truth | inventory, coordination, observation random draws, predictor identity |
| `kappa` | `0.25..2.0` | resource inventory/roster only | hazard, truth, channel, activation multipliers |
| `mu` | `0.5..3.0` | activation, travel, staging, and turn-around friction | inventory, hazard, truth |
| `iota` | `0.3..1.0` | reporting, delay, duplication, error, callback, communication uptime, and controller-visible sensing availability | latent truth, physical resource inventory, physical hazard |
| `phi` | integer `1..9` | authority partition, sharing latency/loss, approval and coordination behavior | raw reports, truth, physical inventory |
| `pi` | `0.3..1.0` | within-predictor prior/calibration profile | predictor identity, truth, observation channel |
| `epsilon` | versioned vector profile | synthetic placement, occupancy, trajectories, and vulnerability | meteorology/hydrology, resource inventory |
| `delta` | `0.0..0.6` | initial resource/facility outage, shelter occupancy, fatigue, degradation | meteorology/hydrology, latent population placement |

Downstream causal consequences are allowed. For example, `sigma` may change truth incidents because it changes hazard, and `phi` may change outcomes because evidence arrives later. Axis isolation does not mean output invariance beyond the axis’s causal descendants.

### 14.2 Keyed random streams

Random draws shall be derived from stable semantic keys rather than consumption order. At minimum, use separate namespaces for:

- geography placement;
- person/structure attributes;
- trajectories;
- meteorology perturbations;
- hydrology residuals;
- breach candidate audit;
- incident candidates;
- observation reporting;
- duplicates/revisions/conflicts;
- location error;
- coordination delivery;
- resource degradation;
- crew schedules;
- fault injection;
- policy tie-breaking;
- bootstrap/inference.

Changing one axis shall transform the relevant mechanism while retaining common underlying uniform/normal draws wherever mathematically meaningful. Tests shall verify both invariant upstream artifacts and expected causal downstream differences.

## 15. Metrics and estimands

### 15.1 Independent sampling unit

The mission seed is the primary independent unit. Calls, incidents, commitments, observations, and repairs within a mission are clustered and shall not be treated as independent observations for inference.

### 15.2 Scenario/process validation

Report by phase and mission:

- latent incident total and taxonomy;
- public report total and hourly/phase intensity;
- non-reporting, duplicate, multi-channel, callback-failure, revision, conflict, false-report, and authenticated-false fractions;
- location method and per-mission error summaries;
- coordination latency/loss by authority;
- roster/occupancy consistency;
- physical conservation and state-bound checks;
- crossing and route-state transitions;
- resource arrivals and crew availability.

### 15.3 Reconciliation and identity

After runtime, compare controller belief clusters with hidden reference clusters and report:

- pairwise precision, recall, and F1;
- adjusted Rand index;
- false-merge and missed-link rates;
- false-report merge rate;
- revision-link precision/recall;
- reported occupant-revision truth accuracy;
- controller occupant-belief accuracy as a separate metric;
- unresolved and disputed identity counts at censoring.

### 15.4 Operational outcomes

Report:

- incident coverage and report coverage separately;
- allocations, refusals, HOLD, BLOCK, and ESCALATE;
- arrival, service, and completion times with censoring;
- people/incident service completed, active, partial, failed, and unknown;
- resource and crew utilization;
- strict/uncapped/historical load metrics and unserviceable windows;
- authority and mutual-aid activation delays;
- executable-safe-alternative use and missed opportunity.

No clinical or casualty outcome is inferred.

### 15.5 Consistency and audit

Report:

- point and extended stale executions under exact declared hazard labels;
- consistency violations;
- evidence age and validity slack at authorization;
- false clears and false holds, with denominators;
- trigger family, channel disposition, and verification cost;
- predictor/calibration guard holds and unsafe high-consequence clears;
- chain validity, replay validity, and attribution completeness;
- record volume, append latency, verification latency, and storage size.

### 15.6 Recovery and compensation

Report:

- fault detection coverage and latency;
- true affected-set precision, recall, F1, and exact-match rate;
- repair work and restoration latency;
- compensation invocation, completion, partial, failure, and retry;
- residual violations/debt at censoring;
- duplicate-effect prevention after silent success;
- restart recovery point and deterministic continuation;
- partial/contradictory outcome resolution accuracy.

### 15.7 Policy estimands

Policy comparisons must predeclare one or more explicit estimands, such as:

- paired mean difference in mission-level consistency violations;
- paired mean difference in completed service at matched verification/compute cost;
- paired mean difference in repair work or restoration latency;
- noninferiority in consistency with superiority in coverage/completion;
- Pareto frontier over cost, staleness, coverage, completion, and recovery.

A weighted-loss composite is secondary unless its units, weights, and consequence semantics are frozen before outcome access. Lower staleness alone is not an operational win.

The recommended primary base-Reference comparison is adaptive TRACE versus the cost-matched nonadaptive operating point chosen on the selection set and accepted without retuning on the validation set. The primary consistency endpoint should be a mission-level paired difference in stale/invalid execution or unresolved consistency debt; the primary service endpoint should be completed eligible service or incident coverage at censoring. The exact endpoint hierarchy and noninferiority/superiority margins require Dr. Chang's manuscript-level approval before confirmatory freeze. The recommended recovery comparison is compensation-enabled TRACE versus the prevention-only ablation under the same faulted worlds. These two comparisons answer different questions and shall not be collapsed into one favorable composite.

## 16. Experimental governance

### 16.1 Study roles

Use four non-overlapping seed namespaces:

1. **development**: unrestricted implementation, coefficient fitting, diagnostics, and fault reachability;
2. **selection**: fixed-fold comparison of candidate methods/operating points using already-declared candidates;
3. **validation**: one-time gate on the selected method and frozen endpoints;
4. **confirmatory**: untouched seeds, remote original execution only after preregistration.

All development and selection seeds are permanently spent. Validation seeds become spent on first execution. Confirmatory seeds shall not be materialized, imported, logged, or run locally.

### 16.2 Coefficient and method fitting

Fit only on development seeds:

- incident-type intercepts;
- observation-phase/reporting coefficients;
- synthetic location/error distributions where not analytically fixed;
- reduced-order physical coefficients not directly sourced;
- fault reachability settings;
- candidate policy operating points.

Record every candidate, objective, input hash, convergence status, and rejected/adverse result. Never normalize an individual seed to a target or tune the illustrative Reference seed.

### 16.3 Freeze sequence

Before confirmatory seed derivation, commit:

- protocol and ambiguity decisions;
- complete scientific-input manifest;
- source/build manifests and license registry;
- scenario and fault profiles;
- coefficients and calibration reports;
- candidate-selection report;
- primary/secondary estimands and multiplicity family;
- acceptance gates and noninferiority margins;
- environment/lock hashes;
- exact code and workflow;
- confirmatory seed derivation rule and count.

Then derive the exact seed list once, commit it, push the preregistration commit, and execute the authorized remote workflow once. A failed gate is published without retuning or replacing seeds.

### 16.4 Original and replication roles

The earliest successful authorized workflow on the immutable preregistration commit is the original. Its report shall bind source commit, workflow/run ID, protocol, manifests, environment, locks, seed list, policy identities, and execution role.

Replication is disabled until the original report and digest registry are committed. Later executions must validate the original report byte-for-byte and label themselves `replication`; they cannot replace it.

## 17. Statistical analysis

### 17.1 General rules

- Analyze at mission-seed level.
- Use common-random-number paired contrasts where policies share exogenous worlds.
- Do not pool calls or commitments as independent samples.
- Report denominators, censoring, zero-opportunity missions, and undefined cells.
- Use intention-to-run denominators: failed runtime missions remain outcomes unless excluded by a predeclared infrastructure rule.
- Report all primary gates and adverse results.

### 17.2 Intervals and tests

Default proposed methods:

- deterministic 10,000-resample paired mission-cluster bootstrap for means and paired differences;
- cluster bootstrap for fractions by recomputing numerator and denominator within each resample;
- exact binomial order-statistic intervals for medians where applicable;
- paired max-`t` simultaneous bands for predeclared metric families when dimension and sample size support them;
- exact sign-flip sensitivity for symmetric paired endpoints when predeclared;
- Monte Carlo error for interval endpoints and p-values.

Bootstrap seeds shall derive from the protocol hash and metric identifier. Empty-denominator bootstrap draws receive a conservative declared treatment and their frequency is reported.

### 17.3 Acceptance versus inference

Engineering invariants are exact gates. Synthetic process targets use predeclared tolerances. Policy efficacy requires intervals and effect/noninferiority criteria. Do not convert a descriptive development target, including approximately 2,900 calls, 95 reports/hour, or approximately 4:1 load, into a confirmatory claim after observing results.

### 17.4 Sample-size determination

Before confirmatory seeds are derived, freeze a minimum practically relevant paired effect, type-I error allocation, target power, minimum and maximum mission count, and stopping rule. Estimate variance only from spent development/selection missions or a justified conservative bound. Compute the confirmatory count once, round upward, and commit it before materializing seeds. No optional stopping, outcome-dependent seed replacement, or post-hoc enlargement is permitted. If the maximum feasible sample cannot provide the declared power, state that limitation and treat the affected result as estimation rather than a definitive test.

## 18. Provenance, replay, environment, and publication

### 18.1 Determinism claim

The exact claim shall be:

> Scenario artifacts are determined by the seed plus the fully expanded, versioned scientific-input bundle. Runtime artifacts additionally depend on the versioned policy, predictor/qualification, fault profile, and execution semantics.

Do not claim that seed and a short parameter tuple alone are sufficient.

### 18.2 Scientific-input manifest

The complete manifest shall include:

- all transitive source modules used by generator, runtime, recovery, validation, and publication;
- scenario, geography, governance, physical, breach, exposure, observation, resource, fault, policy, predictor, qualification, and acceptance inputs;
- source/build manifests and calibration tables;
- environment contract and hash-locked dependencies;
- registered workflow.

Exclude generated reports, figures, bundles, caches, and execution receipts to avoid self-reference. Hash canonical path, length, and content. Import-closure and mutation tests shall prove completeness.

### 18.3 Replay artifacts

Commit a compact canonical Reference seed bundle only if size and data licenses permit. Otherwise commit a checksummed manifest and deterministic generation workflow, with CI/release artifacts holding the larger bundle.

Replay shall verify:

- every scientific/public/hidden artifact digest;
- TRACE and event hash chains;
- commitment-to-record links;
- crash-prefix reconstruction;
- provider idempotency receipts;
- byte-identical decisions after clean regeneration;
- no network access;
- explicit validation inputs rather than ambient files.

Scientific deterministic artifacts exclude runtime-specific timestamps and platform details. A separate execution receipt records interpreter, platform, dependency inventory, source commit, container digest, CI run, and wall time.

### 18.4 Environment

Provisionally continue Small's digest-pinned Python 3.11 OCI reference-environment policy with complete hash-locked dependencies for Reference evidence; freeze a newly resolved image digest before validation. General package support may remain broader. The protocol shall record exact timezone behavior, locale, floating-point/runtime assumptions, and external executable versions.

## 19. Security, privacy, and compliance

Reference is synthetic but must be treated as if it were a deployable evidence pipeline.

- No real names, phone numbers, residential addresses, patient data, credentials, dispatch frequencies, or authentication secrets.
- No unrestricted third-party data or weights committed without license review.
- Pickle-free model/data loading.
- Caller-supplied trusted roots and relative artifact locators.
- Reject root/intermediate/file symlinks, path traversal, non-regular files, oversized files, malformed archives, duplicate archive names, decompression bombs, extra NPZ arrays, non-finite tensors, and digest mismatch.
- Atomic downloads and receipts.
- Network disabled during runtime, replay, validation, and publication.
- Mocked transports for source-refresh tests.
- Artifact schemas use `extra="forbid"`, size limits, and referential integrity.
- Public logs/manifests are scanned for hidden truth IDs and synthetic callback material not intended for release.
- Authentication fixtures use project-owned test keys and deterministic rotation; no production trust claim.
- Threat model and limitations document malicious report content, replay, key compromise, provider duplication, crash consistency, and source-data poisoning.

## 20. Testing and CI

### 20.1 Unit and contract tests

Required coverage includes:

- canonical encoding, fixed-point arithmetic, and keyed randomness;
- geometry transforms, routing, and source/build security;
- meteorology/hydrology components and conservation;
- breach onset, width/inflow bounds, inundation, and crossing/access consequences;
- exposure trajectories, episode formation, and candidate thinning;
- zero/one/many observation channel and `iota` monotonicity;
- authentication and identity-dispute evidence;
- authority partition and sharing latency;
- resource capability, mutual-aid, crew, duty/rest, and strict matching;
- all eight axes and onset category;
- predictor request/provenance/qualification;
- TRACE records, commitments, outcomes, revisions, and compensation;
- crash/restart, reordered delivery, silent success, partial outcome, and failed compensation;
- replay/tamper detection and scientific-input closure;
- statistics and report-model round trips.

### 20.2 Core invariants

Exact acceptance gates:

- Small committed artifacts remain byte-identical.
- Ground truth precedes observations.
- Hidden lineage deletion leaves public runtime artifacts byte-identical.
- No public artifact contains truth IDs or real personal data.
- Every durable allocation cites one exact authorizing TRACE record/version.
- No high-consequence action clears on a missing, superseded, mismatched, or unqualified predictor/calibration tuple.
- One physical resource/crew cannot serve two concurrent commitments.
- Generated travel consumes time-indexed route/access state.
- Services extending beyond the horizon remain active at censoring.
- All event, evidence, TRACE, commitment, provider-receipt, and recovery chains verify.
- Crash/restart reconstructs the same continuation.
- Silent success does not duplicate physical effect.
- Failed compensation produces explicit residual debt.
- Runtime and replay perform no network requests.

### 20.3 Performance

Reference is not subject to Small’s under-one-minute gate. Before validation, profile and freeze a realistic Reference budget in the canonical container.

Provisional engineering targets:

- one full 48-hour burn-in + 96-hour mission generation and execution plus clean replay in at most 15 minutes on the canonical CI runner;
- peak resident memory at most 2 GiB;
- deterministic streaming artifact generation without loading all reports/records into memory;
- full one-seed Reference smoke in scheduled or dedicated CI;
- focused unit/contract suite on every branch update;
- multi-seed development/validation in dedicated parallel workflows.

The 15-minute/2-GiB values are design defaults, not scientific claims. They may be revised once, before validation, from a committed profiling report. The 10% runtime-regression review threshold is likewise provisional and freezes with that report.

### 20.4 Quality gates

- Python formatting and Ruff;
- strict mypy for new Reference, predictor, TRACE, recovery, and shared-support modules;
- architecture/import-cycle checks;
- branch coverage for safety-critical paths;
- `git diff --check`;
- secret, personal-data, license, hidden-truth, unsupported-claim, and scope scans;
- canonical-container replay and report regeneration.

## 21. Implementation phases and gates

### Phase 0 — Protocol and baseline

- Review this ambiguity ledger with Dr. Chang.
- Record the final Small commit and verify its canonical bundles.
- Freeze Reference package boundaries and compatibility policy.
- Create development/selection/validation seed namespaces only.

**Gate:** approved protocol status; byte-identical Small baseline; no confirmatory seed derivation.

### Phase 1 — Geography and governance

- Build source registry, clipped offline geography, ten-crossing network, facilities, levees, gauges, and four logical authority roles.
- Complete spatial, source, license, and security QA.

**Gate:** offline deterministic build; complete referential integrity; all non-operative/approximate fields labelled.

### Phase 2 — Physical state and breach

- Add burn-in, three-pulse meteorology, additive hydrology, levee/anomaly state, reduced-order breach/inundation, and access state.
- Verify units, conservation, bounds, and component audit artifacts.

**Gate:** no hydrodynamic/historical calibration claim; canonical breach exactly once at `T+52`; physical replay exact.

### Phase 3 — Exposure, incidents, and observations

- Generate 1,400-person synthetic cohort, structures, trajectories, truth episodes, candidate audit, and lossy reports.
- Fit incident and observation coefficients on development seeds.
- Add identity disputes, authentication, and authority delivery.

**Gate:** ground-truth-first proof; no truth leakage; fixed coefficients; expected-volume/channel diagnostics documented.

### Phase 4 — Resources and coordination

- Implement T0-T4 rosters, activation/staging/travel, route dependence, crew duty/rest, degradation, request/approval, and capacity accounting.

**Gate:** axis isolation; strict matching; no inventory/arrival or asset/crew conflation; approximate 4:1 remains a reported development target, not a tuned gate.

### Phase 5 — TRACE and recovery

- Integrate full TRACE path, exact predictor qualification, commitment/outcome schemas, fault profiles, restart, idempotency, partial outcomes, and compensation.

**Gate:** every required fault is reachable in development; chains verify; all safety invariants pass; nominal and faulted exogenous artifacts match where required.

### Phase 6 — Reference validation harness

- Add registered studies, statistics, report models, replay, manifests, and deterministic publication artifacts.
- Run development and selection studies.
- Freeze one selected operating point and execute validation once.

**Gate:** validation acceptance; no confirmatory access; all adverse results retained.

### Phase 7 — Optional LEAP study

- Only after base Reference validation, implement the post-admissibility deliberation interface and matched baselines.
- Use a separate protocol and seed namespace.

**Gate:** TRW authorization supremacy, charged deliberation latency, complete audit record, and independent evidence that the method improves a declared frontier on development/validation.

### Phase 8 — Confirmatory freeze and original execution

- Freeze code, data, coefficients, policy, endpoints, margins, environment, manifests, and workflow.
- Materialize confirmatory seeds exactly once.
- Obtain explicit authorization for branch push and original remote execution.
- Publish pass or failure without retuning.

**Gate:** verified original report and registry; full replay; complete limitations and delivery report.

## 22. Proposed acceptance gates

Before confirmatory execution, freeze exact numerical tolerances from analytical expectations and development evidence. At minimum, acceptance shall require:

### Exact gates

- all invariants in Section 20.2;
- one and only one canonical Reference breach;
- zero overlapping incident episodes with identical episode keys;
- zero hidden-truth reads by online runtime;
- zero unsafe predictor qualification clears;
- complete fault-family reachability in the registered faulted profile;
- exact clean replay and tamper detection;
- Small byte preservation;
- canonical performance and memory limits;
- complete source/license/security checks.

### Frozen synthetic-process gates

- expected observed total approximately 2,900 with a tolerance frozen before validation;
- the configured expected peak of 95/hour lies within a predeclared interval for the realized count in the analytically selected fixed peak-hour bin from A21;
- observation-channel fractions and error summaries fall within absolute tolerances;
- latent truth and report totals vary across seeds rather than being forced;
- all four authorities contribute evidence across the registered development ensemble, and a predeclared fault-integration fixture exercises at least one cross-authority revision without entering policy-efficacy estimands;
- nonzero allocation, refusal/HOLD, evidence-driven repair, compensation, and failed-compensation outcomes across the development ensemble;
- a predeclared deterministic integration fixture exercises allocation, refusal or HOLD, visible-evidence revision, and recovery paths; that fixture is excluded from policy-efficacy estimands, while any illustrative Reference seed is reported exactly as realized with no outcome-content gate.

### Report-only targets

- the inherited approximately 4:1 breach-load expectation under the exact historical definition, if that definition can be reconstructed, plus strict and sensitivity load definitions reported without any requirement that they agree;
- historical-source contextual comparisons;
- LEAP or learned-predictor efficacy unless governed by a separate frozen protocol.

If a report-only target is adverse, publish it. Do not revise resources, formulas, or seeds after confirmation.

## 23. Decisions requiring Dr. Chang versus autonomous execution

### 23.1 Dr. Chang review or confirmation recommended

These choices materially affect scientific scope or manuscript claims:

1. Confirm that `T-48..T0` is burn-in and the 96-hour inferential window is `T0..T+96`.
2. Confirm that approximately 2,900 reports refers to the evaluation window, not burn-in plus evaluation.
3. Approve or replace the four logical authority roles under `phi=4`.
4. Confirm whether Reference is intended to update the current TRW paper, a later revision, the book, or a separate integration paper.
5. Approve the primary Reference policy question and consistency/coverage noninferiority margins before confirmation.
6. Confirm whether the faulted profile is part of the headline Reference estimand or an integration stress study.
7. Confirm that LEAP remains optional and separately evaluated rather than required for base Reference completion.
8. Confirm which source-supported gauges or thresholds he expects to be decision-operative.

Engineering may proceed under the proposed defaults if a response is delayed. The project must nevertheless resolve and record these choices before any affected validation or confirmatory freeze; it must not infer manuscript claims from silence.

### 23.2 Autonomous decisions unless contradicted

The following can be executed without additional domain information:

- authoritative-source research, licensing review, clipping, provenance, and offline builder;
- typed package architecture and compatibility facades;
- new keyed-randomness namespaces and CRN tests;
- reduced-order physical implementation with explicit limitations;
- synthetic cohort and privacy-preserving fixtures;
- truth-first incident and observation mechanisms;
- exact TRACE/predictor provenance and qualification;
- secure artifact loading, canonical manifests, replay, and CI;
- development-only coefficient fitting and diagnostics;
- fault-injection engineering and recovery tests;
- report generation and adverse-result retention;
- preserving Small byte-identically on a separate branch.

Autonomy does not authorize changing confirmatory outcomes, manuscript claims, historical facts, or material scientific definitions after validation/holdout access.

## 24. Freeze checklist

This draft may become a preregistration only after every item is resolved:

- [ ] Dr. Chang-required scope and ambiguity decisions recorded.
- [ ] Active TRW manuscript revision mapped to intended Reference claims.
- [ ] Small final commit and bundle hashes recorded.
- [ ] Geography/source/license registry complete.
- [ ] Four logical authorities approved and documented as simulation roles.
- [ ] Burn-in and evaluation denominators frozen.
- [ ] Reduced-order physical and breach coefficients frozen with model card.
- [ ] Truth and observation calibration reports frozen.
- [ ] Resource/crew/tier tables and capacity semantics frozen.
- [ ] Nominal and faulted profiles frozen.
- [ ] Predictor/policy/qualification artifacts frozen.
- [ ] Primary estimands, margins, multiplicity, and sample size/power analysis frozen.
- [ ] Complete scientific-input manifest and canonical environment verified.
- [ ] Development and selection complete; validation run exactly once and accepted.
- [ ] Confirmatory seed derivation committed but not executed locally.
- [ ] Original remote workflow reviewed and authorization procedure recorded.

Until this checklist is complete, every result is development evidence and must be labelled accordingly.
