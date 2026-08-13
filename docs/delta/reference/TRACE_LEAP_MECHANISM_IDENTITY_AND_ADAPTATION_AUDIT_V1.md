# TRACE–LEAP Mechanism-Identity and Adaptation Audit

| Field | Value |
|---|---|
| Status | Pre-engineering ground-truth audit; no TRACE–LEAP effectiveness result |
| Version | `trace-leap-mechanism-identity-audit-v1` |
| Date | 2026-08-11 |
| Disclosure | Local planning evidence; do not present as a TRACE–LEAP result |
| Authoritative method name | LEAP — Lookahead Escalation on Ambiguity for Planning |
| Frozen paper | *Look Before You LEAP: Selective Lookahead Under Ordinal Ambiguity* |
| Intended use | Correct the proposed TRACE/TRW adaptation before any LEAP implementation or experiment |

## Executive decision

The prior TRACE–LEAP plan identified a defensible integration seam but generalized
the evaluated method too aggressively. The corrected design must separate three
layers:

1. **TRACE safety and evidence semantics**, which determine admissibility,
   authorization, physical refresh, commitment, and compensation;
2. **the identity-preserving LEAP core**, which completely scores the eligible root
   choices with exactly two ordinal signals, triggers additional branch computation
   only when the equal-weight Borda top set is nonunique, searches only that top set,
   divides a fixed branch budget equally by floor division, and selects from the best
   branch response with a frozen symmetry-preserving tie rule; and
3. **the Flood-SAR adaptation**, which defines response bundles, two public score
   functions, the counterfactual transition model, branch response, work quantum,
   latency accounting, and mission constraints.

Only layer 2 is the evaluated LEAP mechanism. Layers 1 and 3 are necessary system
design. They must be named, frozen, and ablated separately. This distinction is
scientifically important: otherwise a positive or negative result could not be
attributed to LEAP rather than to candidate construction, score design, rollout
model error, cost accounting, or TRACE gating.

The recommended first implementation remains the post-adequacy,
pre-commitment response-bundle seam. It is an **adapted LEAP policy**, not a literal
reuse of Mini Jump actions or score functions. The appropriate primary policy name
is `trace_leap_response_bundle_v1`; the exact evaluated-domain policies retain their
own names and are never silently conflated with it.

No LEAP code, development result, selection result, or holdout result was produced
as part of this audit.

## 1. Source custody and authority

### 1.1 Frozen authoritative sources

The following frozen materials take precedence over informal summaries and over
later experimental code in the dirty WGS working tree:

| Source | Role | SHA-256 / identity |
|---|---|---|
| `/Users/jaylanroy/Desktop/LEAP_final/paper_final.pdf` | Final paper and claim boundary | `932ce24f0b5a3ab1cdf216a61f3f7cf55ad8af9a678251482c277653444f30ac` |
| `/Users/jaylanroy/Desktop/LEAP_final/technical_supplement_final.pdf` | Full methods, diagnostics, transfer evidence, and limitations | `db6fa36cdf92ddfc4338c6c0f465f63797ccf63ec92e984b1bf76fa0e4522e6b` |
| `LEAP_final/mini-jump-aaai27/artifact/replay_capsule/evaluated/mini_jump_chess/agents/ordinal_arbitration.py` | Byte-exact evaluated Mini Jump trigger, screen, allocation, response, and RNG tie policy | `ce1adc405dbeae853e018203ef14ba0f7c953ccd1c47676f15759233c76aabdb` |
| `WGS/.../aaai-artifact-ipc-update/artifact/evaluated_source/ordinal_arbitration.py` | Independently located artifact copy of the same evaluated policy | same SHA-256, byte-identical |
| `LEAP_final/.../voc_ipc_confirmatory_policy.py` | Frozen Ferry/Gold Miner four-policy decision rule | `fb64cb7dc7ffc338418ed35e81579049f3dd5f57f2a2fdf05050b05586b2df1c` |
| `LEAP_final/.../voc_ipc_schedule_end_to_end.py` | Frozen cross-domain root scoring, trajectory execution, work, and semantic tie choice | `fe95e98f519253442b975742f88bf593899db3a487eaa0a951f1fd95e22b141c` |
| `LEAP_final/.../voc_ipc_confirmation_worker.py` | Frozen branch-prefix and response-curve construction | `2912cb79d2ea4c1a00bc3ffbfd683a69f66127322dbc08c3e28fa8df1d5a9dd8` |
| `LEAP_final/.../FROZEN_SOURCE_BINDING.json` | Source binding for the transfer study | archival source manifest `0801258c...`; protocol `1377b2c3...` |

The working `paper-ipc-update/main.tex` and supplement were read for source-level
detail, but the WGS repository is dirty and user-owned. Their current working-tree
hashes are recorded for auditability, not treated as a new scientific freeze:

- `main.tex`: `d14a0a647bcdb2ced1ca54947b4f9f136b51c43b5cc4628b5d67db863b41e6b7`;
- `supplement.tex`: `52b00d69ee5f59150946a705d6fdaaa6cff9da640fa804eb5310cb3a71a16fc3`.

### 1.2 Materials that are not the evaluated LEAP identity

The following nearby implementations are distinct research methods or development
descendants and must not be used as evidence for the evaluated LEAP mechanism:

| Material | What it is | Why it is not evaluated LEAP |
|---|---|---|
| `src/mini_jump_chess/agents/wgs.py` | Wisdom-Governed Search with auditor shaping, thresholds, masks, and selective deepening | Different scores, gates, search, and selection; not the final LEAP policy |
| `screened_bound_search.py` | Certificate-aware bound search over Borda/Pareto screens | Adds exact/conditional certificates and adaptive frontier allocation; a different method |
| `budget_adaptive_arbitration.py` | Budget-dependent choice of verification breadth | Changes the frozen screen/allocation rule |
| later VoC, metapolicy, stopper, and learned-routing modules | Subsequent development studies | Not identified by the final paper or frozen artifact as LEAP |
| older `paper/main.tex` | Earlier “Borda-Top Lookahead” manuscript | Scientific ancestor; the final identity and evidence are in *Look Before You LEAP* |

These methods may motivate future comparisons, but calling them LEAP would change
the treatment and invalidate mechanism attribution.

## 2. Exact evaluated LEAP mechanism

### 2.1 Decision objects and complete-root requirement

At a decision state `s`, the evaluated method starts from the complete set of legal
root actions `A(s)`. It does not receive an outcome-selected shortlist. Every legal
root successor is constructed and both signals are evaluated before the screen is
formed.

The method's stated scope requires that complete-root scoring fit its declared
action/budget contract. In Mini Jump, `n = |A(s)| <= B`; if complete-root expansion
does not fit, the implementation fails before charging work. In the IPC transfer,
states with more than 64 legal actions are explicitly unsupported; a singleton is
handled directly. Rovers demonstrates that this is a real applicability boundary,
not a minor implementation detail.

### 2.2 Mini Jump signals

For each root action `a`, Mini Jump constructs successor `s_a` and computes:

- **local signal** `L_s(a) = u(s_a)`, where the frozen utility is
  `10 * completion + 2 * target_occupancy + normalized_nearest_target_progress +
  0.1 * remaining_horizon_if_complete`; and
- **structural signal** `S_s(a)`, the equal sum of normalized action-induced
  improvements in maximum nearest-target distance, minimum injective assignment
  sum, and minimum injective bottleneck assignment distance.

These are domain-designed diagnostics. They are not generic definitions of “local”
and “structural,” and they do not transfer unchanged to emergency response.

### 2.3 Tie-aware ordinal fusion

For `n > 1`, each signal is converted independently to the normalized fractional
midrank

```text
r_x(a) = (# values lower than x(a) + 0.5 * (# values equal to x(a) - 1)) / (n - 1)
```

with higher rank better. For `n = 1`, the rank is 1. The equal-weight Borda score is

```text
F(a) = r_1(a) + r_2(a)
```

and the screen is the complete Borda top set `T = argmax_a F(a)`.

The final cross-domain study uses exact doubled-midrank numerators and exact Borda
ties. The registered Mini Jump implementation compared binary floating sums; a
post-hoc exact-rank correction found rare top-set differences and a maximum
completion change of 0.40 percentage points. TRACE–LEAP should use exact integer or
rational midranks from the outset and document that this is the corrected final
form, not reproduce the avoidable floating-tie issue.

### 2.4 Trigger identity

The only LEAP trigger is:

```text
trigger additional lookahead iff |T| > 1
```

It is **not** triggered by:

- disagreement between the two component winners;
- a small cardinal margin;
- entropy, variance, predictive uncertainty, or OOD score;
- stale evidence or a TRACE risk/consequence class;
- a policy-confidence threshold; or
- a mission-wide value-of-computation estimate.

A unique Borda winner is acted on immediately without additional branch search.
Therefore a confidently wrong unique winner is a known failure mode. A margin or
uncertainty trigger is a different method and must be named and evaluated as such.

### 2.5 Screen and budget allocation

When triggered, LEAP searches only `T`. If `k = |T|` and the available branch budget
is `R`, each retained root receives

```text
q = floor(R / k)
```

work quanta. The remainder is unused. Branches are independent; unused work from an
exhausted branch is not transferred to another branch. Large top sets therefore
dilute per-branch search.

The two evaluated instantiations use different, explicitly documented accounting:

| Instantiation | Complete-root cost | Branch budget | Work quantum |
|---|---|---|---|
| Mini Jump | Charged inside total per-decision cap `B`; `R = B - n` | Remaining cap | One generated successor |
| Ferry/Gold Miner | Static complete-root heuristic work is recorded separately | Fixed `R = 64` after scoring | One nonstale A* frontier pop |

Thus “LEAP always subtracts root evaluations from the rollout cap” is false as a
cross-domain identity claim. The stable core is equal allocation to the ambiguous
Borda top set under a frozen domain-specific cost contract. TRACE–LEAP must choose
and name its accounting rather than pretend the papers specify a universal work
unit.

### 2.6 Branch search and response

Mini Jump starts one best-first search at each retained root successor, prioritizes
states by the same utility `u`, de-duplicates seen states within the branch, and
records the maximum utility observed, including the root, as `V_q(a)`.

The Ferry/Gold Miner transfer adapts this to reopening A* over SAS states. Its queue
is ordered by `(g + LM-cut, hFF, LM-cut, g, insertion_order)`. The response after a
nonstale pop is:

- `1 / (1 + g)` when a goal is popped;
- otherwise `1 / (1 + best_frontier(g + LM-cut))`;
- initially `1 / (1 + initial_LM-cut)`; and
- zero after exhausted/dead prefixes, with the terminal value repeated to the
  response horizon.

One nonstale pop may generate and score many successors. The branch cap is therefore
not a generated-successor cap. The artifact records nonstale pops, stale removals,
operator examinations, generated/admitted states, heuristic calls, frontier size,
and wall time separately. Any TRACE claim about compute must likewise report the
full raw vector, not convert heterogeneous work to a fictional common unit.

### 2.7 Final selection and ties

LEAP selects the retained action(s) with the best branch response at their allocated
quota. Mini Jump then samples uniformly from a stable ordering using the decision's
seeded RNG. This is equivariant in distribution, not necessarily pathwise invariant
under a reordered random stream.

The cross-domain schedule uses a deterministic semantic hash over the tie-stream
salt, semantic task digest, state digest, and action digest, and chooses the minimum
hash. Across frozen independent salts this is the transfer implementation of the
uniform symmetry rule and is stable to enumeration order.

TRACE–LEAP should use the semantic-hash realization because it supports canonical
replay and order invariance. The tie salt must be predeclared and paired across
policies. This is an implementation adaptation, not evidence that any deterministic
first-action tie break is equivalent.

## 3. What the evidence supports

### 3.1 Mini Jump

The final paper reports 1,000 prospectively generated tasks, five paired streams,
and a 64-successor-expansion cap per decision. The task is the inferential unit.
LEAP improves completion over Static Borda by 3.68 percentage points on core tasks
and 6.48 points on the shift macro. It uses 65.5% as many successor expansions per
episode as all-action lookahead and 72.2% as many as Pareto lookahead. The trigger
fires on 52.6% of decisions; the mean triggered top-set size is 2.85.

Pareto completion is descriptively close, but no equivalence test was registered.
This supports a selective completion–work operating point in Mini Jump, not Pareto
equivalence and not universal planning superiority.

### 3.2 PSR-small and Rovers

In the separately frozen 54-task end-to-end study:

- on 38 PSR-small tasks, LEAP and always-Pareto record identical action sequences
  across 190 task-stream episodes while LEAP generates 27.6% fewer successors;
- the LEAP-versus-Borda completion contrast is underpowered/inconclusive; and
- Rovers repeatedly violates the complete-root `n <= 64` scope, with no method
  completing a task under the fixed protocol.

Rovers is an applicability failure, not evidence of a quiet trigger or successful
transfer.

### 3.3 Ferry and Gold Miner

The final confirmation uses 360 tasks—180 per generator family—balanced across ten
fixed strata, four policies, and five paired tie streams (7,200 cells). LEAP improves
PDDL-valid completion over Static Borda by 5.56 percentage points with a 95%
stratified paired interval of [3.63, 7.49], and exceeds all-action lookahead by 11.83
points while generating 27.2% as many successors.

Always-Pareto completes 15.50 points more often than LEAP and uses 5.18 times as
many successors. Static Borda, LEAP, and always-Pareto occupy nondominated
completion–work points. LEAP invokes positive lookahead on 20.92% of recorded
decisions versus 98.58% for always-Pareto.

The effect is heterogeneous: +8.67 points in Ferry and +2.44 in Gold Miner, with
Gold Miner near the floor and its gain concentrated in one stratum. The inferential
scope is the fixed balanced mixture of these two generator families conditional on
technical acceptance. It is not a planning-domain superpopulation and does not
establish general emergency-response transfer.

### 3.4 Claims that remain unsupported

The LEAP evidence does not establish:

- that Flood-SAR naturally produces exact Borda ambiguity;
- that proposed Flood-SAR signals retain high-quality response paths;
- that branch computation improves TRACE commitments;
- that a response-bundle formulation is better than action-only planning;
- that LEAP reduces physical sensing or compensation cost;
- that rollouts can replace physical observations;
- that the method is latency-efficient on heterogeneous hardware; or
- that later WGS, screened-bound, VoC, or learned metapolicies are LEAP results.

## 4. Line-by-line audit of the existing TRACE plan

| Existing concept | Audit disposition | Required correction |
|---|---|---|
| Post-adequacy response-bundle seam | Defensible adaptation | Keep, but state that bundles are not original legal actions and test action-only versus bundle construction |
| “Local and structural score” as generic LEAP identity | Overgeneralized | Rename to `signal_1`/`signal_2` in the core; define Flood-SAR service and flexibility signals as adaptation-specific |
| Complete eligible catalog | Required but previously implicit | Require exhaustive deterministic enumeration of all eligible bundles; no outcome-selected shortlisting |
| Root evaluations always consume rollout cap | Incorrect across final evidence | Freeze a TRACE accounting profile; report mandatory screen cost separately from branch budget and total costs |
| Exact Borda tie as default | Correct | Use exact doubled-midrank integers; make exact nonunique top the only canonical LEAP trigger |
| Quantized, margin, Pareto “trigger candidates” | Misleading terminology | Treat as separately named non-LEAP controls/variants; Pareto in the paper is an always-on screened comparator |
| Equal floor allocation | Correct | Preserve unused remainder and forbid adaptive work transfer in canonical LEAP |
| Arbitrary rollout backend | Incomplete | Freeze transition, branch order, response statistic, censoring, and cost quantum before evaluation |
| Seeded final tie | Directionally correct | Use semantic salted hash, paired across arms; document distributional symmetry |
| Per-mission budget | New mechanism | Keep only as an outer TRACE constraint or named ablation; canonical LEAP has a reset per-decision cap |
| Physical sensing and acquisition bundles | New system layer | Keep under TRACE; never label simulated rollout as refresh or LEAP evidence |
| Deliberation latency and stale-after-search reassessment | Necessary TRACE adaptation | Keep and charge it; it is not part of original LEAP evidence |
| Hidden-truth exclusion | Correct and stronger than source domains need | Preserve as a non-negotiable Flood-SAR invariant |
| Static Borda, all-action, Pareto controls | Supported | Match candidates, signals, backend, tie streams, and accounting exactly |
| Matched-cardinality screen | Valid diagnostic | Label post-hoc/mechanism control, not an evaluated canonical baseline |
| Oracle screen | New diagnostic | Restrict to offline evaluator and never expose to runtime |
| “Calibration-free system” | Too broad | Only rank fusion and exact-tie trigger avoid fitted cross-signal scale/threshold; signals, models, and TRACE probabilities may be calibrated |
| “LEAP improves cost–consistency” | Unsupported | Treat as falsifiable local question; no claim until separately governed evidence exists |

No malicious fabrication was found. The problem was mechanism drift through generic
terminology: reasonable Flood-SAR design choices had been described too close to the
LEAP identity. The corrections are realistically worth making before engineering
because they determine policy code, baselines, budget fairness, and claim validity.

## 5. Frozen TRACE adaptation specification

### 5.1 What remains identical to LEAP

The canonical `trace_leap_response_bundle_v1` arm shall preserve:

1. a complete, deterministic root catalog within a declared maximum cardinality;
2. exactly two finite scalar signals evaluated for every catalog member;
3. tie-aware exact fractional midranks, higher-is-better after sign declaration;
4. equal-weight Borda sum with no fitted cross-signal weights;
5. additional branch computation only for a nonunique exact Borda top set;
6. search restricted to that top set;
7. equal floor allocation of the branch budget, unused remainder, no adaptive
   transfer among branches;
8. independent branch computation from each retained root;
9. selection by the frozen response at the allocated quota; and
10. a predeclared symmetry-preserving semantic tie rule.

Changing any of items 2–9 creates a named non-LEAP or modified-LEAP arm and requires
a protocol revision.

### 5.2 Necessary Flood-SAR adaptations

| Adaptation | Why necessary | Required isolation |
|---|---|---|
| Legal roots become TRACE-eligible response bundles | Separates physical action, evidence acquisition, and safe alternatives without bypassing authorization | Compare bundle catalog with an action-only catalog on spent development worlds |
| TRACE filters before LEAP | Simulation cannot authorize an inadequate or stale action | Feature-off and gate-bypass-impossibility tests; no permissive fallback |
| Two Flood-SAR signals replace Mini utility/assignment score | Mini geometry has no semantic validity for rescue decisions | Freeze component tables; signal-only controls; screen-recall diagnostics |
| Public-belief counterfactual model replaces Mini/IPC transitions | Flood response has time, resources, faults, evidence, and commitments | Model-off/static control; calibration/OOD diagnostics; no hidden truth |
| Domain response replaces maximum Mini utility/A* heuristic response | Completion utility is not the TRACE objective | Freeze response semantics; alternative response functions only on development data and as named variants |
| Branch work quantum becomes one public-model transition | Successor generation is the reproducible unit available in Reference | Also record model calls, nodes, bytes, CPU/wall time, and simulated latency |
| Mandatory screen cost recorded separately from branch cap | Matches final cross-domain transfer and avoids variable catalog size silently consuming treatment dose | Root-inclusive accounting sensitivity; report total work vector for every arm |
| Semantic-hash tie choice | Canonical replay and enumeration-order invariance | Pair salts across arms; permutation/equivariance tests |
| Post-deliberation TRACE reassessment | Evidence may expire while computing or acquiring | Zero-latency diagnostic and real-latency primary analysis |
| Outer mission resource/compute limits | Reference has many decisions and resource contention | Canonical per-decision LEAP plus separate mission-budget overlay ablation |

### 5.3 Canonical budget contract

For the first local study, use the final cross-domain style:

- every policy pays and records complete root-catalog construction and two-signal
  scoring;
- LEAP's dynamic branch cap is a fixed number `B_branch` of public-model transitions
  per decision, reset at each decision;
- Static Borda uses zero dynamic transitions;
- all-action and always-Pareto receive the same `B_branch` and use the same floor
  allocation and branch backend;
- generated transitions, model calls, public-state bytes, feature evaluations,
  simulated latency, wall time, CPU time, physical acquisitions, and compensation
  events are separately recorded;
- the total resource vector is primary; no scalar “equivalent expansion” is invented;
  and
- if catalog cardinality exceeds a predeclared supported maximum, the system records
  `unsupported_catalog_cardinality` and follows a frozen safe TRACE fallback.

This profile is named `trace-leap-branch-budget-v1`. A Mini-style root-inclusive
cap is `trace-leap-root-inclusive-budget-control-v1`, not an undocumented alternate
interpretation.

### 5.4 Canonical signals

The mechanism layer receives only `signal_1` and `signal_2`. The proposed Reference
adapter supplies:

- `signal_1 = immediate_service_signal_v1`: current-belief, consequence-aware,
  deadline-sensitive service value net of the bundle's immediate physical delay and
  cost components, expressed as a transparent finite scalar; and
- `signal_2 = future_flexibility_signal_v1`: current-belief preservation of scarce
  capabilities, reachable future commitments, route/resource flexibility, and
  recovery options under the same public model.

These are design candidates, not inherited LEAP truths. Before any effectiveness
study, the components, signs, missing-data behavior, bounds, and public inputs must
be frozen. Their cardinal magnitudes are never added to one another; only exact
midranks enter Borda.

### 5.5 Catalog completeness

`ResponseBundleCatalog` must certify that it is the complete output of a versioned,
deterministic enumeration function applied to the public proposal set and TRACE
eligibility receipt. No policy may shortlist by score before Borda, remove an option
because of hidden future outcome, or see a different catalog.

Duplicate semantic bundles must be either retained with distinct public action
contracts or deduplicated by a frozen policy-independent equivalence rule. The
deduplication receipt is part of the catalog provenance. Cardinality failure is
reported rather than silently truncating the catalog.

### 5.6 Counterfactual branch and response contract

For every retained root:

1. fork the same canonical controller-visible snapshot;
2. apply the root bundle in a simulation-only type;
3. execute exactly `q` permitted public-model transitions or stop on terminal/
   explicit censoring;
4. do not mutate live evidence, TRACE state, clocks, queues, commitments, files, or
   randomness belonging to another branch;
5. compute `response_v1` from the best declared public-belief mission state reached,
   including the root response at quota zero;
6. record the complete response curve and raw work curve; and
7. never convert a rollout into physical evidence or authorization.

The exact `response_v1` objective must be specified before code is interpreted as
LEAP. A generic “rollout score” placeholder is not sufficient for an experiment.

## 6. Required baselines and adaptation ablations

### 6.1 Identity-matched core arms

All core arms use identical catalogs, signals, public snapshots, model backend,
branch response, tie streams, and cost instrumentation:

1. **Base Reference:** existing non-LEAP selector;
2. **Static Borda:** exact two-signal Borda, no branch computation;
3. **TRACE–LEAP:** exact nonunique-Borda trigger, Borda-top search, equal branch cap;
4. **All-action lookahead:** always search all catalog roots under the same branch cap;
5. **Always-Pareto:** always search the nondominated exact-rank set under the same
   branch cap.

Static Borda isolates the value of additional branch computation. All-action
isolates concentration. Always-Pareto supplies a broader screened quality/work
reference and is not expected to use equal realized work.

### 6.2 Required adaptation ablations

| Ablation | Question isolated |
|---|---|
| Action-only roots versus response bundles | Does bundling evidence acquisition with reassessment help, or merely enlarge/design the action space? |
| `signal_1` only and `signal_2` only | Does either proposed score family carry the result alone? |
| Matched-cardinality random/hash screen | Is Borda top-set content better than merely using the same breadth? |
| Always search Borda top | Does the exact ambiguity trigger save work without harming decisions? |
| Same trigger, search all roots | Does concentration rather than trigger timing cause any gain? |
| Root-inclusive versus branch-only budget | Is the conclusion an accounting artifact? |
| Canonical per-decision budget versus mission overlay | Does cross-decision scarcity change the mechanism? |
| Real declared latency versus zero-latency diagnostic | Does computation make evidence stale enough to erase benefit? |
| Public model versus model-off/static | Is any apparent benefit attributable to counterfactual quality rather than screening? |

Quantized-tie, margin, entropy, uncertainty, learned-router, successive-halving, or
adaptive-reallocation policies may be explored only as separately named development
methods. They are not “LEAP variants” in a primary identity comparison unless the
paper explicitly defines a broader family.

## 7. Evaluation and governance corrections

### 7.1 Development-only applicability gates

Before an internal holdout, spent development data must establish:

- supported catalog cardinality at the intended Reference decision points;
- nontrivial exact Borda ambiguity incidence;
- retained-set size and per-branch quota distributions;
- top-set response regret and offline screen recall, clearly labeled evaluator-only;
- deterministic cost conservation and branch isolation;
- absence of hidden-truth and future-event access;
- stable TRACE authorization and feature-off equivalence; and
- acceptable latency/staleness rates.

If exact LEAP rarely triggers, the scientifically correct result is an applicability
failure. Do not tune quantization or a margin on the same holdout and continue to call
the method LEAP.

### 7.2 Local optimization loop

Development may compare a small, predeclared grid of signal definitions, response
definitions, branch budgets, and adaptation choices using only spent development
seeds. Preserve every attempted configuration, input hash, result, adverse finding,
and rejection rationale. Select once on a separate internal selection set under
safety and consistency guardrails. An optional internal holdout requires Jay's
separate approval and a new freeze.

Local effectiveness numbers, seed lists, plots, and optimization logs remain
`LOCAL/INTERNAL ONLY`. They are not committed or pushed without Jay's approval and
cannot become paper evidence retroactively.

### 7.3 Primary estimands

The local question is whether TRACE–LEAP improves the service–consistency–cost
frontier relative to the matched controls. Report:

- completed eligible service and deadline-weighted refusal/delay;
- unauthorized/invalid execution, stale authorization, commitment invalidation,
  and time to compensation/invariant restoration;
- exact physical acquisition cost and latency;
- exact compute/work vector and deliberation latency;
- trigger incidence, retained size, quotas, response-induced choice changes, and
  top-set regret;
- catalog unsupported rate and safe-fallback rate; and
- paired mission-level effects with the scenario seed as inferential unit.

Never optimize or conclude from triggered decisions alone; triggering is endogenous.
Use mission-level paired worlds with common random numbers across policy arms.

## 8. Failure modes and stop conditions

| Failure | Interpretation | Required action |
|---|---|---|
| Catalog is incomplete or outcome-shortlisted | Root-screen identity invalid | Stop; fix enumeration before any LEAP result |
| `n` exceeds supported maximum frequently | Rovers-like applicability failure | Report; redesign scope under a new protocol, not by truncation |
| Exact trigger rarely fires | Ordinal ambiguity does not transfer | Report applicability failure; do not silently widen trigger |
| Unique wrong Borda winner | Known LEAP blind spot | Report offline; margin trigger is a different arm |
| Top set omits best response | Score/screen failure | Diagnose signals; branch search cannot recover omission |
| Large top sets yield zero/small quota | Budget dilution | Report and compare broader controls; do not reallocate adaptively in canonical arm |
| Rollout helps predicted response but harms realized mission | Model/objective error | Report calibration/OOD and paired harm; no planning-gain claim |
| Compute makes evidence stale | Latency defeats authorization | TRACE HOLD/acquire; charge full cost |
| LEAP changes eligibility or writes evidence | Safety-contract violation | Stop; no scalar benefit can rescue the method |
| Later WGS/VoC code is substituted | Treatment identity changed | New name, protocol, baselines, and evidence namespace |

## 9. Corrected implementation sequence

1. Complete and validate the non-LEAP Reference system and G3 handoff interfaces.
2. Freeze a complete, deterministic eligible-catalog contract and cardinality bound.
3. Implement exact two-signal midranks/Borda, Static Borda, and semantic tie streams.
4. Freeze the public counterfactual branch, response curve, branch work quantum, and
   raw cost vector.
5. Implement canonical TRACE–LEAP, all-action, and always-Pareto through identical
   interfaces.
6. Add TRACE reassessment, evidence noninterference, branch isolation, cost, and
   provenance tests.
7. Run constructed fixtures, then spent development applicability diagnostics.
8. Freeze the small adaptation/ablation grid before any selection run.
9. Perform local selection once, preserving all losing/adverse candidates.
10. Ask Jay before creating or opening any internal holdout, and again before
    committing or pushing any effectiveness material.

## 10. Remaining decisions and information

No additional historical fact is needed to identify LEAP. Before the first
TRACE–LEAP effectiveness run, the project must still freeze adaptation-specific
choices that the LEAP paper cannot supply:

- the exact complete response-bundle grammar, deduplication rule, and supported
  catalog cardinality;
- the component formulas and public inputs for the two Flood-SAR signals;
- the public-model branch order, response statistic, censoring rule, and transition
  work quantum;
- the branch budget grid and compute-to-simulated-latency mapping;
- the service/consistency endpoint hierarchy and consequence-derived guardrails;
  and
- whether Jay authorizes an internal holdout after development and selection.

These can be chosen autonomously for local development under the existing
development/selection governance. Dr. Chang's approval is needed before converting
the selected adaptation into a manuscript-level confirmatory protocol or changing
the intended paper claim. The non-LEAP Reference G3/G4 freeze is a hard engineering
prerequisite.

## 11. Audit conclusion

There is more than one viable way to integrate LEAP into TRW. The evaluated mechanism
does not determine whether roots should be raw actions, evidence-acquisition paths,
response bundles, or recovery choices; it determines how a complete set of root
choices is ordinally screened and when/how bounded branch work is concentrated.

The response-bundle seam remains the strongest first scientific test because it
directly exposes TRW's observation/computation/commitment trade-off without allowing
simulation to masquerade as evidence. Its benefit is not guaranteed. The corrected
protocol makes the test falsifiable and attributes outcomes to the LEAP core versus
the necessary Flood-SAR adaptation.

The corrections are worth making before engineering. They require no change to the
delivered Small simulator or the non-LEAP Reference scientific mechanics, and they
prevent the most consequential paper risk: reporting a custom TRACE planner under
the LEAP name without isolating what actually transferred.
