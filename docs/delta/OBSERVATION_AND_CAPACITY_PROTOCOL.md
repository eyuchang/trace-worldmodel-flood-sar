# Generator-v8 observation, reconciliation, outcome, and load protocol

## Causal boundary

Keyed structure/tick/type hazards generate candidate draws before any report.
Continuous eligibility episodes suppress repeated accepted candidates until the
enabling state clears or the affected subject set changes. This prevents a
persistent condition from being mislabeled as several incidents while
preserving distinct simultaneous incident types.
The configured hourly report profile calibrates fixed observation coefficients;
it never creates truth and is never solved separately for an evaluated seed.

The zero/one/many channel supports non-reporting, first and third-party reports,
duplicates, multi-channel evidence, conflicting reports, revisions, callback
failure, dropping, false benign levee reports, and imprecise locations. Public
calls contain no truth relationship or person/incident identifier.

At `iota=0.9`, location methods target 55% GPS/address intersection, 27%
landmark, and 18% cell sector. Frozen precision ranges are 15–75 m, 200–800 m,
and 400–1,500 m. Lower information quality monotonically transfers probability
toward cell sector and scales ranges by `0.9 / iota`, capped at 3×. Reporting,
duplicates, multi-channel evidence, conflicts, revision, callback failure, and
dropping also degrade monotonically.

Descriptions use a small taxonomy-conditioned vocabulary. Reports from one
incident probabilistically share a descriptor family, but the same descriptors
occur across unrelated incidents; no public token uniquely identifies lineage.

`phi` controls a separate coordination artifact. Unified immediate delivery is
used at `phi=1`; higher test values partition source authorities and delay
evidence sharing deterministically. Truth, raw calls, physics, and inventory are
unchanged.

## Hidden/public artifacts

- Controller-visible raw calls contain report content and uncertainty.
- Coordination contains only logical source/delivery information.
- Controller decisions contain visible relationship evidence and belief IDs.
- Hidden lineage links reports to synthetic truth for offline evaluation only.

Deleting lineage yields byte-identical decisions, evidence, TRACE records,
commitments, and outcomes. If lineage is absent, offline reconciliation is
explicitly marked unavailable; the controller does not fail or change behavior.

## Reversible controller evidence graph

Each public call is a node. Proposed links are `confirmed`, `suspected`,
`rejected`, or `superseded`. Valid revision pointers and exact available shared
callback tokens are hard confirmation. Soft confirmation requires time within
1,500 seconds, uncertainty-aware spatial compatibility, exact taxonomy, at
least descriptor or occupant/medical corroboration, one eligible destination
cluster, a post-merge span no longer than 1,800 seconds, and no visible cluster
contradiction. Ambiguous soft links remain suspected and separate.

The frozen candidates `evidence-graph-q075`, `q100`, and `q125` differ only in
their spatial uncertainty multiplier. Five development folds selected q075 by
the preregistered false-merge/recall rule. Confirmatory evaluation is paired by
seed against the immutable v7 heuristic, with false-merge improvement primary
and recall noninferiority margin −0.05.

## Complete reconciliation evaluation

Every set of reports from one non-null truth incident is a reference cluster.
Every false report is its own singleton. The full controller partition is scored
after runtime using:

- pairwise precision, recall, and F1;
- false-merge and missed-link rates;
- false-report merge rate;
- revision-link precision and recall;
- reported-occupant-revision truth accuracy (an observation-channel measure,
  not controller performance);
- adjusted Rand index without a heavyweight dependency.

Immutable pre-v8 reports retain their prior scores under their historical
label. That score is not used as complete reconciliation accuracy.

## Incident and resource contracts

Every incident declares one capability, service duration, service units, route,
and causal mechanism. Every resource declares capabilities, service units,
base/origin, route, activation/transit/staging/travel time, availability, and
service duration.

The roster is unchanged from v6: a local rescue boat and Type I engine plus a
preauthorized Rio Vista Zodiac and Type I engine staged at T+5,400 seconds.
Boats support water rescue and missing-person search; engines support medical,
road rescue, welfare checks, and levee inspection. Engines cannot satisfy water
rescue. `service_units=2` is a synthetic analytical rubric, while every physical
resource can hold only one concurrent commitment.

## Intrinsic load measures

All intrinsic measures use active ground-truth incidents and the frozen resource
schedule at fixed 15-minute points, independent of policy and predictor choice.

### Primary: strict concurrent load

Each scheduled, mobilized, reachable, available physical resource may match at
most one compatible active incident and must have at least the incident's
required units. Matching maximizes incident service units completely covered.
Active demand is divided by that strict matched capacity.

### Sensitivity: uncapped compatible-service-unit load

Each eligible physical resource compatible with at least one active incident is
counted once at its declared service units, without capping capacity to demand.

### Historical sensitivity: registered normalized coverable load index

The v6 calculation assigns each resource to one capability/route bucket and caps
its service units within aggregate bucket demand. It remains reproducible as
`registered_normalized_coverable_load_index`. The historical v6 value of 1.5
belongs only to this registered definition and is never called conventional
demand/capacity in v8.

Empty demand yields zero for every measure. Positive demand with no compatible
capacity is explicitly unserviceable and has no finite ratio. The primary
strict ratio has no numerical pass/fail gate and the resource roster will not be
retuned after it is observed.

## Residual strict pressure

After TRACE execution, an active commitment removes truth demand only if its
physical resource is capable, sufficiently sized, scheduled, available, and
reachable for the true incident. Remaining incidents are matched to free
resources using the same one-resource/one-incident semantics. A false-report or
misclassified commitment consumes capacity without erasing truth demand.

## Completion and censoring

Every allocation records the untruncated scheduled completion, the scenario
censoring time, its exact authorizing commitment, and exact TRACE record/version.
Completion observed on or before the six-hour horizon is
`completed_within_window`. Later service remains committed and busy and is
`active_at_scenario_censoring`; it has no observed completion and is never
truncated or relabeled complete.

## Seed-cluster inference

The protocol-v10 reconstruction report treats one seed as one cluster. Means and channel
fractions use deterministic 10,000-resample cluster bootstrap intervals.
Medians use exact binomial order-statistic intervals. Location errors are first
summarized within seed. No interval treats individual calls as independent.

The registered expected point estimates and absolute tolerances are calibrated
from the declared development seeds and frozen in
`configs/scenarios/wf_dfld_01_small_acceptance_v6.yaml`. They are synthetic
process-design checks, not field-validity targets.
