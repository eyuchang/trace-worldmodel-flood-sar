# ADR: WF-DFLD-01-REFERENCE G3 Handoff to Future TRACE–LEAP Engineering

| Field | Value |
|---|---|
| Status | Proposed interface/acceptance ADR; design only |
| ADR version | `reference-leap-handoff-adr-v2` |
| Date | 2026-08-11 |
| Applies to | Non-LEAP WF-DFLD-01-REFERENCE implementation |
| Required by | Reference G3 implementation-complete gate |
| LEAP authorization | **None—this ADR does not authorize LEAP implementation or evaluation** |
| Evidence status | No seeds, experiments, holdouts, or effectiveness claims |

## 1. Decision

The non-LEAP Reference implementation shall expose a stable, typed,
policy-neutral **decision handoff boundary** before base Reference validation. The
boundary lets the base TRACE controller:

1. capture an immutable controller-visible state;
2. construct physical action proposals, physical evidence-acquisition offers, and
   separately authorized safe alternatives;
3. apply TRACE authorization and adequate-set-first channel rules;
4. materialize an ordered catalog of eligible response bundles;
5. select one bundle with the frozen **base Reference selector**;
6. execute any physical acquisition, advance real latency, and reassess;
7. consume and commit only through `TraceRuntime`; and
8. persist costs, receipts, and exact replay provenance.

Reference shall also expose a pure, public-belief counterfactual step port that a
future deliberation adapter can call. The port performs one bounded model transition
and returns a type that is structurally incapable of serving as physical evidence.
It contains no screen, score aggregation, ambiguity trigger, branch allocator,
search policy, or LEAP identifier.

This contract must be implemented by G3 and then exercised unchanged by the G4
base Reference validation. Passing G3 does **not** unlock LEAP experiments. Future
TRACE–LEAP engineering begins only after G4 validation and separate approval.

This boundary is reconciled with
`TRACE_LEAP_MECHANISM_IDENTITY_AND_ADAPTATION_AUDIT.md`. In the evaluated LEAP
domains, candidates are the complete set of legal root actions. Treating eligible
response bundles as roots is a Flood-SAR adaptation. G3 must therefore make the
catalog exhaustive, policy-independent, and provenance-bound; it must not implement
the later ordinal screen or imply that response bundles were evaluated in the LEAP
paper.

## 2. Reconciliation of the two protocols

The Reference protocol says the optional seam is “after TRW constructs admissible
verification/safe-alternative options and before a commitment.” The LEAP plan names
the more exact version a **post-adequacy response-bundle seam**. They mean:

- `ACT_NOW`: a physical action that TRACE currently authorizes;
- `ACQUIRE_THEN_REASSESS`: a physical channel in TRACE's adequate, positive-net-
  value, deadline-feasible set; acquisition is authorized, but the later physical
  action is not pre-authorized;
- `SAFE_ALTERNATIVE`: a lower-consequence physical plan that has received its own
  current TRACE assessment and is authorized under its own contract; and
- `HOLD`, `BLOCK`, and `ESCALATE`: TRACE dispositions/fallbacks outside the bundle
  catalog, never options that a later deliberator can convert into `CLEAR`.

The later LEAP layer may choose how to spend bounded computation among the same
eligible bundles. It may not define eligibility, refresh a claim by simulation, or
commit an action. The base Reference selector must use this boundary first so the
future comparison changes only the declared selection/deliberation policy.

## 3. Architectural placement

```text
Reference event machine
        |
        v
ControllerVisibleStatePort.snapshot()
        |
        v
ReferenceProposalFactory.propose()
        |
        v
TraceEligibilityService.classify()
        |
        v
ResponseBundleCatalog (ordered, eligible only)
        |
        v
BaseReferenceSelector.select()       # no LEAP behavior
        |
        v
EvidenceAcquisitionExecutor, if selected
        |
        v
scenario clock advances by actual receipts
        |
        v
TraceRuntime.assess -> consume -> commit / HOLD / ESCALATE
```

The boundary belongs in the Reference companion package. Domain-independent TRACE
contracts remain in `trace_jepa`; Reference-specific projections and adapters stay
in `trace_reference`. No G3 module may import a future `deliberation` or LEAP
package.

Recommended Reference package surface:

```text
trace_reference/
  decision/
    domain.py          public snapshots, proposals, bundles, receipts
    visibility.py      controller-visible projection and allowlist
    eligibility.py     TRACE authorization and adequate-set classification
    acquisition.py     physical channel execution and receipt ingestion
    selector.py        frozen non-LEAP selector protocol and implementation
    costs.py           unit-preserving cost/latency ledger
    counterfactual.py  pure one-step public-belief model port
    artifacts.py       canonical handoff/replay records
```

## 4. Interfaces Reference shall implement now

These are the complete G3 handoff obligations. None embeds LEAP behavior.

### 4.1 `ControllerVisibleStatePort`

```python
class ControllerVisibleStatePort(Protocol):
    def snapshot(self, *, decision_id: str, at_s: int) -> ControllerVisibleSnapshot: ...
```

`ControllerVisibleSnapshot` is frozen and canonical. It contains only:

- scenario/mission/decision IDs and integer simulation time;
- current public evidence-ledger prefix digest;
- current TRACE-record and commitment-chain prefix digests;
- public weather, gauge, route/crossing, levee, facility, and access beliefs;
- resource, crew, availability, activation, and telemetry beliefs;
- delivered authority/coordination messages and public source identities;
- active public commitments, known outcomes, deadlines, and dependency edges;
- predictor/prior/qualification provenance visible to the controller;
- policy/environment/schema versions; and
- the snapshot's own canonical digest.

It excludes:

- hidden truth, incident lineage, person truth, candidate audit, and evaluator joins;
- future exogenous events, future observations, breach truth not yet observed, and
  unprocessed event-queue payloads;
- real resource state not yet delivered through telemetry;
- hidden fault schedule or future provider outcomes; and
- filesystem paths, open handles, mutable services, or ambient process state.

IDs exposed in the snapshot must already be public runtime IDs; no stable mapping to
hidden truth may be derivable from their construction.

### 4.2 `ReferenceProposalFactory`

```python
class ReferenceProposalFactory(Protocol):
    def propose(self, request: ProposalRequest) -> ProposalSet: ...
```

`ProposalRequest` binds the public snapshot digest, decision deadline, target public
incident/belief cluster, policy version, and deterministic proposal namespace.

`ProposalSet` is a stable tuple of:

- `PhysicalActionProposal`;
- `EvidenceAcquisitionOffer`; and
- `SafeAlternativeProposal`.

Each physical proposal binds:

- exact `ActionInstance` or Reference action-schema equivalent;
- action class, actor/resource/crew, route, destination, and parameters;
- reversibility and consequence class;
- authority requirement and current public authority evidence;
- proposed execution interval and commitment horizon;
- public precondition-claim IDs;
- capability/concurrency/dependency requirements;
- predictor-request/evidence digests; and
- canonical proposal digest.

The proposal factory may enumerate options. It must not rank them using LEAP,
inspect hidden truth, or suppress an option because of its realized future outcome.
It must emit the complete set produced by the frozen public proposal grammar, plus
an enumeration receipt binding the grammar/version, public input digest, generated
count, deduplication decisions, and completeness status. A future selector may not
receive a score-shortlisted subset.

### 4.3 `EvidenceAcquisitionOffer`

Every physical sensing/verification channel must be an explicit offer:

```python
class CostAmount(FrozenModel):
    cost_id: str
    quantity_microunits: int
    unit: str
    schedule_version: str

class EvidenceAcquisitionOffer(FrozenModel):
    offer_id: str
    channel_id: str
    target_claim_ids: tuple[str, ...]
    evidence_schema_version: str
    clear_probability_micros: int
    required_clear_probability_micros: int
    value_of_information_units: int
    physical_cost: CostAmount
    requested_at_s: int
    expected_latency_s: int
    latest_useful_delivery_s: int
    provider_id: str
    provenance_digest: str
```

The clear probability is preposterior adequacy—not a guarantee. Eligibility
requires, before any later selector sees the offer:

- `clear_probability >= required_clear_probability`;
- expected delivery no later than the declared useful/commitment deadline;
- strictly positive root `value_of_information - physical_cost` under the frozen
  base policy's declared common unit; and
- no pending/minimum-interval/provider/authority guard failure.

If value and cost do not share a defensible unit, the offer cannot pass a fabricated
net-value test. The protocol must define the conversion before G3 or retain the base
policy's already-frozen unit mapping and report raw components separately.

### 4.4 `TraceEligibilityService`

```python
class TraceEligibilityService(Protocol):
    def classify(
        self,
        *,
        snapshot: ControllerVisibleSnapshot,
        proposals: ProposalSet,
    ) -> EligibilityReceipt: ...
```

The service must call the same TRACE/policy/qualification contracts used for real
execution. It returns, for every proposal:

- original proposal digest;
- eligibility kind;
- TRACE disposition or channel-adequacy decision;
- exact claim/evidence/record references used;
- failed gates, missing items, authority state, deadline margin, and reason;
- policy, revalidation, predictor, calibration, and qualification versions/hashes;
- classification time; and
- canonical classification digest.

For an acquisition offer, classification authorizes only acquisition. For an
act-now or safe-alternative proposal, `authorization_sufficient_for_action` must be
computed by TRACE for that action/consequence class. No future adapter may reinterpret
`QUALIFY`, `HOLD`, `BLOCK`, or `ESCALATE` itself.

### 4.5 `ResponseBundleCatalog`

```python
class ResponseBundleKind(StrEnum):
    ACT_NOW = "act_now"
    ACQUIRE_THEN_REASSESS = "acquire_then_reassess"
    SAFE_ALTERNATIVE = "safe_alternative"

class ResponseBundle(FrozenModel):
    bundle_id: str
    kind: ResponseBundleKind
    proposal_digest: str
    eligibility_digest: str
    public_snapshot_digest: str
    action: ActionContract | None
    acquisition: EvidenceAcquisitionOffer | None
    deadline_s: int
    consequence_class: str
    fallback_disposition: CommitmentDecision
    schema_version: str
    bundle_digest: str

class ResponseBundleCatalog(FrozenModel):
    decision_id: str
    bundles: tuple[ResponseBundle, ...]
    excluded_proposal_receipts: tuple[str, ...]
    proposal_enumeration_receipt_digest: str
    eligibility_receipt_digest: str
    complete_for_declared_grammar: bool
    trace_prefix_digest: str
    catalog_digest: str
```

Model validation enforces exactly one payload appropriate to the bundle kind.
Ordering is canonical and policy-independent—for example by consequence class,
deadline, kind order, proposal ID, then digest. The future deliberator may not
change membership; it receives this frozen catalog.

`complete_for_declared_grammar` must be true before selection. Catalog construction
includes every TRACE-eligible proposal, records every exclusion, and applies only a
frozen policy-independent semantic-deduplication rule. Unsupported cardinality is an
explicit fail-closed Reference outcome; the catalog is never truncated to satisfy a
future deliberation budget.

The catalog must not contain a `HOLD`, `BLOCK`, or `ESCALATE` bundle. Those remain
recorded outcomes used when the catalog is empty, selection fails, or later
reassessment does not authorize commitment.

### 4.6 `ReferenceDecisionSelector`

```python
class ReferenceDecisionSelector(Protocol):
    selector_id: str
    def select(self, request: BaseSelectionRequest) -> BaseSelectionReceipt: ...
```

Reference shall implement the frozen base selector used for G4 validation. The
request receives the same catalog later adapters will receive. Its receipt records:

- catalog/snapshot/TRACE prefix digests;
- base selector version;
- selected bundle ID or no-selection fallback;
- all root values the base selector actually used;
- deterministic tie rule and tie receipt;
- selection compute receipt and elapsed simulated latency;
- reason and canonical digest.

The G3 selector has no Borda ranks, ambiguity trigger, retained top set, rollout
branches, branch quotas, or LEAP policy ID.

### 4.7 `EvidenceAcquisitionExecutor`

```python
class EvidenceAcquisitionExecutor(Protocol):
    def request(self, bundle: ResponseBundle) -> AcquisitionRequestReceipt: ...
    def ingest(self, provider_receipt: ProviderReceipt) -> AcquisitionOutcomeReceipt: ...
```

It executes only an eligible acquisition bundle and persists:

- request/provider/idempotency IDs;
- offer/bundle/decision digests;
- requested, started, observed, delivered, and ingested times;
- expected and realized physical cost/latency;
- success, timeout, partial, malformed, duplicate, or failed status;
- acquired payload digest and source/authentication metadata; and
- evidence-ledger reference only after schema, digest, source, and timing checks.

Only a valid physical/provider receipt may create new physical evidence. A timeout,
simulation, predictor result, or counterfactual step cannot.

After any acquisition outcome, Reference rebuilds the public snapshot and calls
`TraceRuntime.assess` again. The original acquisition eligibility is never an
action authorization.

### 4.8 `ActionContract` and commitment handoff

```python
class ActionContract(FrozenModel):
    action: ActionInstance
    action_class: str
    consequence_class: str
    reversible: bool
    execution_not_before_s: int
    execution_not_after_s: int
    commitment_horizon_end_s: int
    authority_requirement: str | None
    required_claim_ids: tuple[str, ...]
    dependency_ids: tuple[str, ...]
    idempotency_key: str
    outcome_schema_version: str
    compensation_contract_id: str | None
    digest: str
```

Every durable action must follow:

1. current public snapshot;
2. predictor request/evidence;
3. TRACE `assess` at the post-selection/post-acquisition time;
4. TRACE `consume`;
5. `commit` only if the consumed decision is sufficient for that action class;
6. provider request/receipt and censored or completed outcome; and
7. revision/compensation with exact dependency links when required.

The commitment cites the exact **post-delay** authorizing record/version and the
Reference persists a separate frozen `ReferenceCommitmentEnvelope` that binds the
core commitment ID to the selected bundle and selection-receipt digests. This avoids
silently changing the existing core `Commitment` schema while keeping the domain
handoff replayable. No cached pre-acquisition or pre-delay `CLEAR` may authorize it.

### 4.9 `DecisionCostLedger`

Reference shall preserve raw, unit-labeled components:

```python
class DecisionCostDelta(FrozenModel):
    physical_acquisition_costs: tuple[CostAmount, ...]
    predictor_inference_count: int
    planning_transition_count: int
    primitive_operation_count: int
    bytes_read: int
    bytes_written: int
    decision_latency_s: int
    acquisition_latency_s: int
    service_delay_s: int
    compensation_costs: tuple[CostAmount, ...]
    consistency_violation_units: int
    unserved_service_units: int
    receipt_ids: tuple[str, ...]
```

Reference implements event-derived sensing, base compute, latency, service,
compensation, and violation accounting now. It must not invent one scalar across
incommensurate units. A future deliberation adapter may add separately identified
model-call/successor-expansion costs through the same receipt mechanism; it may not
overwrite base or physical costs.

Clock rules:

- selection, acquisition, provider, communication, and execution latency advance
  integer simulation time according to their receipts;
- all claim ages, deadlines, crew/resource state, and route beliefs are evaluated
  at the advanced time;
- overlapping asynchronous work follows the event machine rather than blindly
  summing durations; and
- every cost is charged exactly once by stable receipt ID.

### 4.10 `PublicCounterfactualModelPort`

Reference shall expose one-step public-belief model dynamics without search:

```python
class PublicCounterfactualModelPort(Protocol):
    model_id: str
    def fork(self, snapshot: ControllerVisibleSnapshot) -> PublicModelState: ...
    def step(self, request: CounterfactualStepRequest) -> CounterfactualStepResult: ...
```

`CounterfactualStepRequest` binds a `PublicModelState` digest, one eligible action
or acquisition model, bounded horizon increment, model/predictor provenance, and a
small explicit compute allowance. `CounterfactualStepResult` contains predicted
public-belief state, predicted outcome distribution, model assumptions, nonfinite/
censor status, and exact compute receipt.

The result must carry `semantic_role="simulation_only"` and must not inherit from,
contain, or be accepted as `WorldModelEvidence`, provider evidence, or an acquisition
receipt. The port:

- receives no live runtime object, hidden truth type, event queue, evaluator, or
  filesystem root;
- cannot mutate live state, evidence, TRACE records, commitments, or clocks;
- performs no network access or ambient file discovery;
- uses only verified, allowlisted immutable model artifacts; and
- has no loop, branching, ranking, screen, trigger, allocation, or selection.

Reference may use this same one-step model for its transparent base prediction. A
future LEAP adapter may orchestrate repeated calls only after G4 and approval.

### 4.11 `ReferenceDecisionArtifactPort`

For every decision, persist canonical public artifacts:

- controller-visible snapshot or a complete reconstructable projection;
- proposal set;
- eligibility receipt and excluded-proposal reasons;
- response-bundle catalog;
- base selection receipt;
- acquisition requests/outcomes, if any;
- pre/post TRACE assessments and evidence references;
- cost/latency deltas;
- commitment/outcome/revision/compensation links; and
- a decision manifest binding every digest and schema.

Hidden truth joins and offline scores remain in separately hashed evaluator
artifacts and are never referenced by runtime artifact paths or IDs.

## 5. Interfaces Reference shall **not** implement now

G3 shall contain none of the following:

- `LEAP`, Borda, Pareto, ambiguity, top-set, screen, or branch-search policy code;
- any LEAP signal definitions or ordinal fusion;
- successor-expansion or mission rollout-budget allocation;
- trigger thresholds, quantization, or margin candidates;
- LEAP development/selection/holdout namespaces or seed loaders;
- effectiveness metrics comparing deliberation policies;
- an offline oracle exposed to the controller;
- code that treats counterfactual output as new evidence;
- a path that bypasses `TraceRuntime.assess`, `consume`, or `commit`; or
- any feature flag whose enabled implementation exists before G4 approval.

Reference may reserve a generic `decision_extension_id: str | None = None` field in
configuration/manifests. At G3, only `None` is valid. Unknown/non-null values fail
closed. This creates an explicit future attachment point without embedding behavior.

## 6. Replay and provenance contract

The G3 scientific-input manifest must include:

- all handoff models, services, schemas, and canonical serialization code;
- base selector and counterfactual-model versions/source hashes;
- Reference scenario/geography/governance/policy/predictor/qualification inputs;
- evidence-channel definitions, costs, latency rules, provider schemas, and
  deterministic tie rules;
- TRACE policy and revalidation implementation;
- environment/lock identity; and
- the exact G3 acceptance tests.

Replay must verify:

- identical public snapshot/proposal/eligibility/catalog/selection bytes;
- identical acquisition request and provider-ingestion behavior;
- identical time advancement and cost receipts;
- identical TRACE records, consumer actions, commitments, outcomes, revisions, and
  compensation; and
- identical decision-manifest digests after restart versus uninterrupted execution.

Runtime-specific execution metadata belongs in a separate receipt and must not make
otherwise identical scientific artifacts differ.

## 7. Feature-off equivalence

At G3, capture a canonical non-LEAP Reference characterization bundle for:

- nominal fixture;
- faulted/restart fixture;
- acquisition-success fixture;
- acquisition-timeout fixture; and
- empty-catalog fallback fixture.

After any future deliberation package is added, executing with
`decision_extension_id=None` must reproduce those artifacts byte-for-byte. The
future package must not be imported, instantiate a backend, consume randomness,
advance time, write files, or alter source-manifest membership on the feature-off
path.

Feature-off equivalence covers the public/scientific artifacts and base cost ledger.
An execution receipt may differ only in explicitly allowlisted source commit/build
identity fields.

## 8. Security and information-flow invariants

1. Public snapshot construction uses an explicit field allowlist, not recursive
   serialization of runtime state.
2. Runtime decision modules cannot import `generation.truth`, hidden lineage,
   evaluator, candidate-audit, or future-event modules.
3. Counterfactual types cannot be passed to the evidence ledger or TRACE assessment
   without a type/schema failure.
4. All IDs, digests, numbers, tuple lengths, timestamps, and schema versions are
   validated; nonfinite values fail closed.
5. Artifact/model inputs use trusted-root relative locators, maximum sizes, digest
   checks, regular-file checks, and intermediate-symlink rejection.
6. No pickle, dynamic code loading, environment-dependent plugin discovery, or
   network access occurs at runtime/replay.
7. Provider receipts are authenticated for source/envelope integrity without being
   declared truthful merely because they authenticate.
8. Duplicate/out-of-order/late provider receipts are idempotent and explicitly
   recorded.
9. A copied public model state cannot mutate live runtime state by shared references.
10. Logs, errors, and public manifests contain no hidden person/incident IDs,
    private callback information, secrets, or real personal data.
11. Resource/crew/route compatibility and one-commitment concurrency apply equally
    to proposals, base model steps, and execution.
12. An unavailable extension or malformed catalog produces the frozen TRACE
    fallback; it never defaults to permissive action.

## 9. Exact G3 acceptance tests

All tests below are exact engineering gates. They use constructed/development
fixtures only and open no validation, holdout, or confirmatory seeds.

### Public state and architecture

- **G3-PUB-001 — allowlist:** snapshot JSON contains every declared public field and
  no hidden/evaluator/future field.
- **G3-PUB-002 — hidden deletion equivalence:** deleting hidden lineage/evaluator
  artifacts before runtime yields byte-identical snapshots through commitments.
- **G3-PUB-003 — public ID independence:** public IDs do not encode hidden IDs or
  truth digests.
- **G3-PUB-004 — immutability:** mutating a forked/public-model object cannot alter
  live state.
- **G3-ARCH-001 — dependency direction:** runtime/decision/counterfactual modules
  have no forbidden imports or import cycle.
- **G3-ARCH-002 — no LEAP:** source/import closure contains none of the prohibited
  policy symbols/modules and accepts only `decision_extension_id=None`.

### Proposal, adequacy, and bundles

- **G3-PROP-001 — deterministic enumeration:** identical public snapshots produce
  identical ordered proposal bytes.
- **G3-ADEQ-001 — inadequate channel excluded:** a channel below the class-specific
  clear-probability threshold never enters the catalog.
- **G3-ADEQ-002 — deadline channel excluded:** an otherwise adequate channel whose
  delivery misses the useful horizon never enters the catalog.
- **G3-ADEQ-003 — nonpositive-net channel excluded:** under the frozen common-unit
  mapping, nonpositive root net value cannot enter the catalog.
- **G3-ADEQ-004 — guard exclusion:** pending/minimum-interval/provider/authority
  guard failures remain excluded and recorded.
- **G3-AUTH-001 — current action only:** `HOLD`, `BLOCK`, `ESCALATE`, or insufficient
  `QUALIFY` cannot produce `ACT_NOW`.
- **G3-SAFE-001 — independent safe assessment:** a safe alternative is excluded
  unless its own action/evidence/consequence assessment authorizes it.
- **G3-BUNDLE-001 — kind invariants:** every bundle contains exactly the allowed
  payload and references the matching eligibility receipt.
- **G3-BUNDLE-002 — canonical membership/order:** catalog membership and byte order
  are independent of proposal input order and base selector behavior.
- **G3-BUNDLE-003 — no fallback bundles:** HOLD/BLOCK/ESCALATE are recorded but not
  catalog members.
- **G3-BUNDLE-004 — exhaustive declared grammar:** constructed finite grammars prove
  the catalog contains every and only eligible proposal, with matching enumeration,
  exclusion, and deduplication receipts.
- **G3-BUNDLE-005 — no shortlist/truncation:** changing base-selector values cannot
  change catalog membership, and an over-limit catalog fails closed with an explicit
  unsupported-cardinality receipt rather than dropping roots.

### Acquisition, time, and commitment

- **G3-ACQ-001 — acquisition is not action authorization:** a selected acquisition
  offer cannot directly commit its downstream action.
- **G3-ACQ-002 — physical receipt only:** only a validated provider receipt creates
  a new evidence-ledger entry.
- **G3-ACQ-003 — failure/timeout:** failed, partial, malformed, duplicate, and late
  receipts follow frozen idempotent outcomes and cannot fabricate evidence.
- **G3-TIME-001 — advanced-time reassessment:** acquisition/selection/provider delay
  advances the clock and claim ages before reassessment.
- **G3-TIME-002 — stale after delay:** an originally authorized proposal becomes
  HOLD when its evidence expires during declared delay.
- **G3-COMMIT-001 — exact authorization link:** every commitment cites the consumed
  post-delay TRACE record/version plus selected bundle/selection digest.
- **G3-COMMIT-002 — no shortcut:** instrumentation proves durable actions traverse
  `assess → consume → commit` and direct policy-engine execution cannot persist one.
- **G3-CONCUR-001 — physical constraints:** proposals/model steps/execution cannot
  double-assign resource, crew, route, or authority capacity.

### Cost and model isolation

- **G3-COST-001 — receipt conservation:** mission totals equal the exact sum of
  unique decision/event receipt deltas.
- **G3-COST-002 — no invented denominator/scalar:** unserviceable/undefined states
  remain explicit and raw cost units remain separately serialized.
- **G3-COST-003 — overlap semantics:** parallel event latency follows event times and
  is not double-summed; sequential latency is fully charged.
- **G3-MODEL-001 — simulation-only type:** `CounterfactualStepResult` is rejected by
  evidence ledger and TRACE evidence schemas.
- **G3-MODEL-002 — no live mutation:** any number of model steps leaves live
  evidence, TRACE, commitments, queue, clocks, and files unchanged.
- **G3-MODEL-003 — public-only sensitivity:** changing hidden truth while holding the
  public snapshot constant leaves model-step bytes identical.
- **G3-MODEL-004 — bounded/offline:** step allowance, size, finite-value, timeout,
  trusted-artifact, and no-network failures all fail closed.

### Replay, restart, security, and preservation

- **G3-REPLAY-001 — exact decision replay:** every handoff/TRACE/cost artifact
  regenerates byte-for-byte in a clean process.
- **G3-REPLAY-002 — restart equivalence:** restarting at each registered boundary
  produces the same continuation and final manifest as uninterrupted execution.
- **G3-TAMPER-001 — digest binding:** changing any snapshot, proposal, eligibility,
  channel, cost, policy, model, or receipt member fails verification.
- **G3-SEC-001 — path safety:** traversal, symlinked roots/intermediates/files,
  nonregular/oversized inputs, malformed arrays/archives, and digest mismatches fail
  closed.
- **G3-SEC-002 — public artifact scan:** no hidden IDs, real personal data, secrets,
  unrestricted assets, or unsupported operational claims appear.
- **G3-OFFLINE-001 — network prohibition:** generation through replay succeeds with
  network disabled and tests fail any attempted request.
- **G3-SMALL-001 — delivered preservation:** every registered Small config, report,
  bundle, figure, manifest, and result-table hash remains exact.
- **G3-CHAR-001 — base characterization:** the five feature-off fixtures and their
  full artifact hashes are recorded as inputs to the future Reference scientific
  freeze.

## 10. G3 handoff artifact

G3 produces one canonical `ReferenceDecisionHandoffManifest` containing:

- ADR/version and implementation source digest;
- mechanism-identity-audit path and SHA-256;
- public schema versions;
- interface/module import closure;
- base selector/model/channel/cost versions and hashes;
- G3 test IDs and passing result hashes;
- five characterization-bundle manifests;
- Small preservation receipt;
- environment/lock identity; and
- an explicit declaration: `leap_implementation_present=false` and
  `effectiveness_evidence_present=false`.

The manifest becomes an input to G4 validation. After G4 passes, a future LEAP
engineering branch may depend on it. If any member changes, the handoff version
changes and base Reference must be re-characterized/revalidated before an
effectiveness comparison.

## 11. Approval and stop conditions

This ADR authorizes only Reference interface implementation and G3 constructed
tests once the parent Reference work is authorized. It does not authorize:

- LEAP code;
- deliberation-policy experiments;
- development/selection/validation/holdout seed execution;
- internal evaluation material in Git;
- a branch push; or
- a manuscript/public effectiveness claim.

Stop the handoff if:

- an interface requires hidden truth or future event access;
- eligibility cannot be decided before future selection;
- physical sensing cost/latency lacks a defensible recorded unit;
- the base selector and future selector would receive different catalogs;
- counterfactual output can enter the evidence ledger;
- feature-off/reference replay cannot be made exact;
- the implementation changes Small bytes; or
- adding the port would require claiming that the reduced-order model predicts real
  Delta operations.

## 12. Acceptance conclusion

Reference is ready to hand off only when it can deliver the exact same immutable
public decision frame to the base selector and a future approved adapter, execute
selected physical evidence channels through receipts, reassess at the advanced
clock, commit only through TRACE, account for every cost and delay, and replay the
entire chain without hidden truth. The handoff deliberately stops at this boundary:
Reference supplies the governed problem and one-step public model, while any later
LEAP layer supplies only a separately authorized method for allocating bounded
computation.
