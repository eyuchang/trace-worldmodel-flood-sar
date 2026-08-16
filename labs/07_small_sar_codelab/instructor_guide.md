# Instructor Guide: TRACE Small End-to-End Flood-SAR

This component is designed for more than 100 college students inside a broader
one-day workshop. Debate and regret are handled elsewhere; this activity owns
the small end-to-end SAR path only.

## What students build

Students complete three functions in a scaffolded rescue controller:

1. deterministic compatible-resource filtering;
2. allocation versus evidence/capacity refusal; and
3. append-only visible-evidence repair.

The provided runtime reads hash-bound public records from the delivered Small
book. It supplies the call, evidence/TRACE authorization, resource view,
commitment link, and outcome link. Student code makes the downstream controller
decision. This is substantial enough to be “implementing SAR” while remaining
feasible and scientifically bounded.

## Non-negotiable scope

- Do not introduce debate or regret code; they are separate workshop topics.
- Do not open hidden truth or hidden lineage for students.
- Do not run development, confirmatory, recovery, reconstruction, or
  replication studies.
- Do not edit the Small policy, configuration, calibration, manifest, or book.
- Do not describe teaching variants as experiments or research results.
- Do not claim operational readiness, field validity, casualty modeling,
  learned-predictor effectiveness, or V-JEPA qualification.
- `CLEAR` means the evidence gate permits use; allocation additionally requires
  compatible, mobilized, reachable, uncommitted capacity.

## Recommended format

### Required route: 3 hours 15 minutes

| Time | Activity | Instructor checkpoint |
|---:|---|---|
| 0:00–0:15 | Rescue story and information boundary | Students can name latent versus visible information |
| 0:15–0:30 | Preflight and triage | Five PASS lines; no live installs after this point |
| 0:30–0:50 | Fresh Small run and exact replay | `8 allocated / 12 refused / 8 repaired`; byte-identical replay |
| 0:50–1:10 | Four-case public walkthrough | Emphasize HOLD versus CLEAR-without-capacity |
| 1:10–1:40 | TODO 1 | Deterministic filtering test passes |
| 1:40–2:15 | TODO 2 | Allocation and both refusal pathways pass |
| 2:15–2:40 | TODO 3 | Prior allocation retained; repair appended |
| 2:40–2:55 | Capacity comparisons | Label every output teaching-only |
| 2:55–3:10 | Committed-book replay | Byte-identical result; registered book untouched |
| 3:10–3:15 | Exit check | One-sentence claim boundary from each table |

Add the README extensions, group explanation, and JSON audit drawing to fill a
half or full day if desired.

### Ninety-minute fallback

1. Run preflight before the session or provide preflighted machines.
2. Show the canonical fresh-run summary rather than waiting for every student.
3. Walk through the four supplied solution cases for 15 minutes.
4. Assign TODO 2 only; provide TODO 1 as an instructor snippet.
5. Pair students for TODO 3 or demonstrate it if fewer than 15 minutes remain.
6. Run the two capacity variants and finish with the claim boundary.

The fallback still shows the complete call → TRACE → controller → commitment →
outcome → repair path.

## Setup decision for 100+ students

Use a local Python environment as the primary route:

- Python 3.11;
- the complete hash-locked Delta requirements;
- an editable install with `--no-deps`; and
- the offline preflight.

The runtime itself completes in under a second on the development machine. A
container is not the primary recommendation: simultaneous image pulls add a
network/quota failure mode, and the exact registered Linux/amd64 environment
may require emulation on Apple silicon. Do not add an untested cloud dependency
on workshop day.

The tested contingency is Python 3.12 with the same hash-locked requirements.
It is acceptable for the teaching loop but is not the canonical book
environment. Native Windows is not certified; prepare WSL or Linux lab machines
in advance.

## Preparation checklist

Complete these no later than the day before:

1. Freeze and record the approved lab commit.
2. Provision the recorded Small base checkout on every managed machine.
3. While network access is available, install the hash-locked environment and
   editable package. The editable step uses an isolated build environment and
   may fetch its build tooling even after runtime dependencies are present.
4. Run preflight on each supported platform image.
5. Run the solution tests and save the short result.
6. Run one fresh Small generation, fresh replay, and committed-book replay.
7. Verify no lab output was written under `data/`, `docs/delta/validation/`, or
   `src/trace_jepa/scenario/delta/`.
8. Disable automatic environment updates until the workshop ends.
9. Put the checkout revision and five preflight PASS labels on the opening
   slide or board.
10. Assign one helper per 25–35 students and one setup lead for escalations.

Do not make the session depend on students cloning or downloading packages at
the same time. Require setup as pre-work or use preprovisioned lab machines.

## Distribute starter files without the solution

The preferred student distribution is:

1. an existing repository checkout at base commit
   `3f912bdf3fbacb679063da9ed2ce15a2330b91ab`; and
2. the deterministic lab-only overlay produced below.

```bash
bundle_root="$(mktemp -d)"
.venv/bin/python labs/07_small_sar_codelab/scripts/make_student_bundle.py \
  --output "$bundle_root/trace-small-sar-student.zip"
```

The overlay contains the student README, starter, runtime, public case
provenance, preflight, and tests. It excludes the solution, this guide, video
files, and all scenario/geography data. Students extract it at the root of the
base checkout.

Do not distribute the full instructor branch if revealing the reference
solution matters. Do not build a new data/container archive from upstream
government assets. Prefer the already hosted repository and preprovisioned
checkouts.

## Instructor verification

Run:

```bash
TRACE_SMALL_SAR_CONTROLLER=solution .venv/bin/python -m pytest -q \
  labs/07_small_sar_codelab/tests
.venv/bin/python labs/07_small_sar_codelab/lab_runtime.py \
  --controller solution \
  --case all
```

Expected controller output:

```text
allocation: TRACE=clear -> allocation (allocated_compatible_capacity), resource=RES-ENGINE-01
evidence_hold: TRACE=hold -> refusal (trace_not_clear), resource=none
capacity_refusal: TRACE=clear -> refusal (no_compatible_capacity), resource=none
visible_repair: allocation@v2 -> repair@v4 (new commitment=false)
```

Before distribution, have someone who did not author the lab complete the
student route without the solution. Record setup time, total time, every point
of confusion, and whether they could explain CLEAR versus allocation. This
human walkthrough is a release gate, not a replaceable automated test.

## Common problems and rapid recovery

| Signal | Response for a large room |
|---|---|
| Python not found | Move the student to a preprovisioned machine; do not troubleshoot package managers live |
| `rasterio` missing | Run the complete lock install; an editable-only install is incomplete |
| Hash mismatch | Quarantine that checkout and replace it from the recorded revision |
| TODO error | Ask which TODO number appears; direct the student to its targeted test |
| Many tests fail at once | Confirm `TRACE_SMALL_SAR_CONTROLLER=starter` and repository-root working directory |
| Replay mismatch | Save logs and switch the student to a clean checkout; never patch the reference book |
| Output already exists | Use a fresh per-student temporary directory |
| Screen-reader difficulty | Use the text architecture alternative and JSON output; pair only with consent |

Use three room-status cards or a shared poll:

- **Setup:** preflight not READY.
- **Code:** preflight ready, a TODO test failing.
- **Explain:** tests pass, ready for interpretation.

This prevents the instructor from diagnosing setup and logic failures in one
queue.

## Teaching notes for each case

### Allocation

TRACE record `trace-a3a193ed42b86e47471e@v2` has a `clear` consumer action.
`RES-ENGINE-01` is compatible, visible, reachable, and available. The public
commitment uses that exact record/version, and the public observed outcome is
`completed_within_window`.

Do not generalize one observed synthetic outcome into effectiveness.

### Evidence refusal

The selected levee-inspection record is held because the observation freshness
gate failed. A compatible resource is visible, but it cannot be committed under
that TRACE consumer action.

### Capacity refusal

TRACE says `clear`, but neither compatible engine is currently available. This
case is the strongest check that students have not collapsed authorization and
allocation into one Boolean.

### Visible repair

A later call shares an exact controller-visible callback token with the earlier
call. Reconciliation explicitly reports `hidden_lineage_used=false`. TRACE
versions 3 and 4 supersede the earlier chain, and the controller appends a
repair. The prior commitment remains part of history; the repair creates no new
commitment.

## Discussion prompts

1. What does the controller know at the decision time, and what is deliberately
   unavailable?
2. Which component owns evidence authorization, and which owns scarce resource
   commitment?
3. Why is deterministic tie-breaking an accountability property rather than a
   performance result?
4. What does append-only repair enable during later review?
5. What cannot be concluded from a complete audit trail?
6. What additional evidence and review would be required before moving from a
   synthetic teaching simulator toward any field-validation study?

## Early finishers

- Add and test a deterministic equal-travel-time tie.
- Mutate a disposable resource view to unreachable and explain the refusal.
- Draw the exact record/version → commitment → outcome references from JSON.
- Compare `completed_within_window` with `active_at_scenario_censoring` without
  labeling the latter success or failure.

Do not let extensions edit canonical inputs or become informal experiments.

## Accessibility and inclusion

- Send the student README and starter before class.
- Keep terminal font at least 18–20 pt during projection.
- Read every error and expected output aloud.
- Use the text alternative rather than requiring Mermaid rendering.
- Allow pairs, but require each student to explain one decision boundary.
- Provide extra setup time without reducing the scientific interpretation task.

## No-network fallback

After initial provisioning, all required execution is offline. Keep:

- preprovisioned repository checkouts;
- preinstalled Python environments for each supported platform image;
- the small student overlay zip; and
- printed or locally hosted copies of the README.

Do not rely on a live package index, Git host, container registry, video host,
or external dataset during class.

## End-of-session evidence to collect

Collect only teaching evidence, not research results:

- anonymous completion count;
- setup issue categories;
- which TODO required the most help;
- one-sentence student explanations of CLEAR versus allocation; and
- accessibility/setup improvements for the next workshop.

Do not pool variant outcomes and report them as a Small experiment.
