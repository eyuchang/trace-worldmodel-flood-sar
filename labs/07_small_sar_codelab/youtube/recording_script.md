# Recording Script: TRACE Small End-to-End Flood-SAR

Target length: **14:50**. The checked-in review draft is screen-only and silent;
its condensed chapter narration is supplied as timed captions. This file is the
full captions-ready transcript. A later human recording may read it without
improvising commands or scientific claims.

## 00:00–00:40 — Title and promise

**Screen:** Title card: “Build an End-to-End TRACE Flood-SAR Controller.” Show
the subtitle “Public evidence → TRACE → dispatch → commitment → outcome →
repair” and badges “No GPU,” “No model download,” and “Offline execution.”

**Narration:**

Welcome. In this lab you will run the delivered TRACE Small Flood-SAR teaching
simulator and finish a controller that turns a TRACE consumer action plus visible
resource state into an allocation or a refusal. You will also append a later
visible-evidence repair and verify deterministic replay. The exercise uses no
GPU, learned-model checkpoint, flood video, or live data.

## 00:40–01:40 — Learning objectives and scope

**Screen:** Student learning objectives on the left; limitations on the right.

**Narration:**

The goal is one complete, understandable rescue path—not a reimplementation of
the full research simulator. You will distinguish hidden world state from what
the controller can see, follow exact TRACE record versions, implement dispatch
and repair, and explain why CLEAR is not allocation. Small is synthetic and
reduced-order. It is not an operational emergency-response system. Student
variants are teaching outputs, not research results. Debate and regret are
covered separately in the workshop.

## 01:40–02:55 — Architecture and ownership

**Screen:** Animate or reveal the architecture from the student README one step
at a time.

**Narration:**

A synthetic call reaches the controller through a lossy public observation
stream. The Toy predictor produces controller-visible evidence. TRACE records
the claim, evidence references, verdict, and consumer action. Your code begins
at the downstream rescue-controller boundary. It checks whether TRACE permits
use and whether compatible, reachable, available capacity exists. An allocation
creates a commitment linked to the exact TRACE record and version. A later
visible report can append a repair. Latent truth exists for offline scoring but
is never an input to your controller.

## 02:55–03:55 — Preflight

**Screen:** Clean terminal at repository root, 20-point monospace font.

**Command:**

```bash
.venv/bin/python labs/07_small_sar_codelab/scripts/preflight.py
```

**Expected output:** five PASS lines and:

```text
READY: no GPU, model checkpoint, or live data connection is needed.
```

**Narration:**

Run preflight before the room starts coding. It checks the supported Python
version, repository files, complete dependency set, hashes of the public
teaching inputs, and a private temporary output. It performs no network request
and does not write scientific artifacts. If a hash check fails, replace the
checkout; never edit a manifest to make the warning disappear.

## 03:55–05:00 — Fresh run and exact replay

**Screen:** Run the commands, then highlight the event counts and replay line.

**Commands:**

```bash
sar_work_root="$(mktemp -d)"
.venv/bin/trace-jepa-delta-small run --output "$sar_work_root/run"
.venv/bin/trace-jepa-delta-small replay \
  --reference "$sar_work_root/run" \
  --output "$sar_work_root/replay"
```

**Expected highlights:**

```text
allocated=8 refused=12 repaired=8
replay is byte-identical
```

**Narration:**

The fresh deterministic scenario runs quickly and produces eight allocations,
twelve refusals, and eight visible-evidence repairs. These are synthetic
controller events, not real rescue counts. Replay regenerates the run in a
clean directory and compares every byte. Exact replay establishes identity to
the named inputs and code; it does not establish real-world correctness.

## 05:00–06:30 — Four public cases

**Screen:** Run the public-book walkthrough and reveal each row separately.

**Command:**

```bash
.venv/bin/python labs/07_small_sar_codelab/lab_runtime.py \
  --controller book \
  --case all
```

**Expected output:**

```text
allocation: TRACE=clear -> allocation (allocated_compatible_capacity), resource=RES-ENGINE-01
evidence_hold: TRACE=hold -> refusal (trace_not_clear), resource=none
capacity_refusal: TRACE=clear -> refusal (no_compatible_capacity), resource=none
visible_repair: allocation@v2 -> repair@v4 (new commitment=false)
```

**Narration:**

The first case has both TRACE clearance and available compatible capacity. The
second has capacity but TRACE holds the action because a hard technical gate
failed. The third is crucial: TRACE clears, but no compatible resource is
currently available, so the controller refuses. The fourth appends a repair at
record version four while retaining the earlier commitment. The walkthrough is
rendered directly from hash-checked public book events; it does not reveal the
student solution.

## 06:30–07:45 — TODO 1: eligible resources

**Screen:** Open `starter/rescue_controller.py` and highlight only TODO 1. Show
the four predicates and deterministic sort key beside the editor.

**Narration:**

Your first function filters the visible resource list. Keep a resource only if
it is currently available, route-reachable, on the requested route, and has the
required capability. Then sort by routed travel time and resource ID. That
second key prevents input order from changing the dispatch when travel times
tie. Do not hard-code the example engine.

**Test:**

```bash
TRACE_SMALL_SAR_CONTROLLER=starter .venv/bin/python -m pytest -q \
  labs/07_small_sar_codelab/tests/test_controller.py \
  -k eligible_resources
```

## 07:45–09:15 — TODO 2: authorization and capacity

**Screen:** Decision table:

| TRACE | Compatible capacity | Controller event |
|---|---|---|
| not CLEAR | any | evidence refusal |
| CLEAR | none | capacity refusal |
| CLEAR | available | allocation |

**Narration:**

The second function first validates that the request and authorization name the
same call and belief cluster. A consumer action other than CLEAR must refuse
before examining dispatch options. With CLEAR, call your filtering function. No
eligible resource produces a capacity refusal; otherwise allocate the first
deterministic resource. This ordering preserves the boundary between evidence
authorization and scarce-resource commitment.

**Test:**

```bash
TRACE_SMALL_SAR_CONTROLLER=starter .venv/bin/python -m pytest -q \
  labs/07_small_sar_codelab/tests/test_controller.py \
  -k "clear_plus_capacity or hold_refuses or clear_without_capacity or mismatched"
```

## 09:15–10:30 — TODO 3: append-only repair

**Screen:** Show `allocation@v2 → repair@v4`, with version 2 remaining visible.

**Narration:**

The repair function starts with an existing decision history. Require the same
belief cluster and TRACE record chain, a later version, and a nonempty visible
evidence basis. Return the old tuple plus one repair event. Do not replace the
old allocation and do not create a second commitment. Append-only history lets
a reviewer see what the controller represented and why it acted at each time.

**Test:**

```bash
TRACE_SMALL_SAR_CONTROLLER=starter .venv/bin/python -m pytest -q \
  labs/07_small_sar_codelab/tests/test_controller.py \
  -k repair
```

## 10:30–11:30 — Focused tests and student run

**Screen:** All tests pass, then run the four-case student controller.

**Commands:**

```bash
TRACE_SMALL_SAR_CONTROLLER=starter .venv/bin/python -m pytest -q \
  labs/07_small_sar_codelab/tests
.venv/bin/python labs/07_small_sar_codelab/lab_runtime.py \
  --controller starter \
  --case all
```

**Narration:**

Run the entire focused suite. It checks normal behavior, malformed links,
visible-only access, source hashes, protected output paths, documentation, and
determinism. Then run your controller end to end. Your four decisions should
match the public walkthrough. Matching does not mean you rebuilt the whole
simulator; the scaffold owns artifact loading and contract validation, while
your code owns the downstream controller choices.

## 11:30–12:45 — Teaching-only capacity comparisons

**Screen:** Side-by-side output: CLEAR plus no capacity refuses; CLEAR plus
restored capacity allocates. Keep “TEACHING-ONLY” visible throughout.

**Commands:**

```bash
.venv/bin/python labs/07_small_sar_codelab/lab_runtime.py \
  --controller starter --case allocation --variant no-capacity
.venv/bin/python labs/07_small_sar_codelab/lab_runtime.py \
  --controller starter --case capacity_refusal --variant restore-capacity
```

**Narration:**

These comparisons change copied resource views inside the lab only. Removing
capacity turns the cleared allocation case into a capacity refusal. Restoring
one visible resource turns the cleared capacity case into a lab allocation.
Neither command changes TRACE, the canonical book, or a registered result. Do
not pool these outputs or call them an experiment.

## 12:45–13:45 — Committed-book replay

**Screen:** Run the committed-book replay and highlight “byte-identical.”

**Command:**

```bash
.venv/bin/trace-jepa-delta-small replay \
  --reference data/scenario/delta/reference/wf_dfld_01_small_book_v6 \
  --output "$sar_work_root/book-replay" \
  --validation-report docs/delta/validation/WF_DFLD_01_SMALL_VALIDATION_V6.json
```

**Narration:**

Finish by replaying the committed book with its bound report. The expected
message says the replay is byte-identical to the book directory. The retained
evidence is an authorized artifact-reconstruction replication after original
and recovery artifact-retention failures. Describe that history exactly; do not
call the book untouched confirmation.

## 13:45–14:50 — Interpretation and close

**Screen:** Final checklist and limitations statement.

**Narration:**

You have run the real Small teaching simulator, followed public TRACE evidence
to an exact record version, implemented dispatch and both refusal pathways,
preserved a repair, and verified replay. The audit chain explains what the
controller represented and why it acted. It does not prove that the represented
claim was true, the action was optimal, or the system is ready for emergencies.
Small is synthetic and reduced-order, the Toy predictor is a teaching fixture,
and every student variant remains non-experimental. Use the README for reset,
troubleshooting, accessibility, and optional extensions.

## Final on-screen limitations statement

Keep this card visible for at least 12 seconds:

> WF-DFLD-01-SMALL is a deterministic, synthetic, reduced-order teaching
> simulator using controller-visible evidence and simulation-grade geography.
> It is not operational emergency-response validation. The Toy predictor and
> student variants are not evidence of learned-model effectiveness or new
> research results. The retained book is artifact-reconstruction evidence.
