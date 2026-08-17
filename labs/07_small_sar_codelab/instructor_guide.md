# Instructor Guide: Flood Rescue Controller Lab

This component is designed for more than 100 college students inside a broader
one-day workshop. Assume students know basic Python but have **no prior SAR or
TRACE knowledge**. Debate and regret are handled elsewhere.

## The teaching goal

By the end, students should be able to explain and implement this distinction:

```text
TRACE asks: Is the information ready to use?
The controller asks: Is a suitable response unit available?
```

The central takeaway is that TRACE `CLEAR` allows a resource check; it does not
send a unit.

Students should also be able to explain that the simulation has a hidden
answer key, while the controller decides only from the evidence it is allowed
to see.

## Begin with the rescue story—not the repository

Open with this scenario before showing a terminal:

> A welfare-check call arrives during a flood. The information may be ready to
> use, and two response units appear on the dispatch board. Should the system
> send one? If not, what reason should it record?

Then reveal the path:

```text
call -> evidence -> TRACE -> student controller -> allocation or refusal
                             \
                              later information -> append a repair
```

Do not begin with scientific provenance, seed history, validation roles,
artifact names, or claim disclaimers. Those are instructor responsibilities,
not prerequisites for understanding the rescue decision. The student materials
use one plain safety sentence: this is a simulation for learning, not a real
emergency tool.

## What students build

Students complete three functions in `starter/rescue_controller.py`:

1. `eligible_resources`: keep units that are available, reachable, on the
   requested route, and capable of the task; then sort them repeatably.
2. `decide_rescue`: combine TRACE's decision with the eligible-resource list to
   return allocation, information refusal, or capacity refusal.
3. `apply_visible_repair`: append a later record correction while preserving
   the earlier allocation.

The runtime supplies the calls, evidence, TRACE decisions, resource snapshots,
commitment links, and saved outcomes. Student code owns the final controller
decision.

## Vocabulary sequence

Introduce terms only when the story needs them:

| When | Introduce | Student-facing explanation |
|---|---|---|
| Opening | SAR | Search and rescue: finding, reaching, and helping people during an emergency |
| System path | Hidden answer key | The simulation's complete made-up story; the controller cannot read it |
| System path | Evidence | Information the software is allowed to use |
| System path | TRACE | The decision notebook that records what is believed and whether a proposal may move forward |
| TRACE decision | `CLEAR` / `HOLD` | Continue to the resource check / stop because information is not ready |
| Resource check | Capability | A task a response unit can perform |
| Controller output | Allocation / refusal | Select a unit / select none and record why |
| Later update | Repair | A record correction, not a physical repair |
| TODO 2 | Belief cluster | A group of calls believed to describe the same situation |
| TODO 3 | Record version | A numbered snapshot that preserves the decision timeline |
| Replay | Byte-identical | Every saved file matches exactly |

Prefer the student-facing wording throughout the live lesson. Use internal terms
only if a student asks to inspect the JSON.

## Recommended format

### Required route: 3 hours 15 minutes

| Time | Activity | Instructor checkpoint |
|---:|---|---|
| 0:00–0:20 | Welfare-check story, SAR, the hidden answer key, and the five-step system path | Students can say what the controller can see, what TRACE checks, and what their code checks |
| 0:20–0:35 | Preflight and room triage | Five PASS lines and `READY` |
| 0:35–0:55 | Fresh scenario and replay | Students can explain the three counts and `byte-identical` |
| 0:55–1:20 | Four-case guided walkthrough | Students distinguish information refusal from capacity refusal |
| 1:20–1:50 | TODO 1: eligible units | Resource-filter test passes |
| 1:50–2:25 | TODO 2: allocate or refuse | All allocation/refusal tests pass |
| 2:25–2:50 | TODO 3: later correction | Version 2 remains; repair version 4 is appended |
| 2:50–3:05 | Full tests, student run, and two what-if changes | Students explain why capacity changes the result while TRACE stays CLEAR |
| 3:05–3:15 | Saved class replay and exit explanation | Each group states the call → TRACE → controller path |

Pause for the README's checkpoint questions. The room should not proceed from
the four cases to code until students can explain why Cases 2 and 3 both refuse
for different reasons.

### Ninety-minute fallback

1. Provide preflighted machines and show the fresh-run summary.
2. Spend 15 minutes on the welfare-check story and four completed cases.
3. Ask every student to complete TODO 2.
4. Provide TODO 1 as an instructor snippet after explaining the four filters.
5. Demonstrate TODO 3 if fewer than 15 minutes remain.
6. Run both capacity what-if examples.
7. End by having students explain `CLEAR` versus allocation in their own words.

The fallback still covers the complete call → TRACE → controller → recorded
decision path.

## Facilitation prompts

Use questions that keep the class inside the story:

- “What question has TRACE answered so far?”
- “What does the simulation know that the controller is not allowed to read?”
- “What question is still unanswered before we send a unit?”
- “A unit is visible. Why might we still refuse?”
- “TRACE says CLEAR. Why might we still refuse?”
- “What should happen to version 2 when version 4 arrives?”
- “Which line of your code records the reason for this decision?”

Avoid asking students to recite schema or provenance language.

## Setup decision for 100+ students

Use local Python as the primary route:

- Python 3.11;
- the complete hash-locked Delta requirements;
- an editable install with `--no-deps`; and
- the offline preflight.

The runtime completes in under a second on the development machine. A container
is not the primary recommendation because simultaneous image pulls add network
and quota failures. Python 3.12 is the tested local contingency. Native Windows
is not certified; prepare WSL or Linux machines in advance.

Do not make the live session depend on 100 students cloning or installing at
once. Require setup as pre-work or use prepared lab machines.

## Preparation checklist

Complete these no later than the day before:

1. Freeze and record the approved lab commit.
2. Provision the recorded Small base checkout on every managed machine.
3. While network access is available, install the locked environment and
   editable package.
4. Run preflight on every supported platform image.
5. Run the solution tests and save the short result.
6. Run the fresh scenario, fresh replay, four-case walkthrough, both what-if
   cases, and saved class replay.
7. Confirm the projected terminal can display every walkthrough line without
   horizontal scrolling.
8. Disable automatic environment updates until the workshop ends.
9. Prepare three room-status cards: Setup, Code, and Explain.
10. Assign one helper per 25–35 students plus one setup lead.

## Distribute the starter without the solution

The preferred distribution is:

1. an existing repository checkout at base commit
   `3f912bdf3fbacb679063da9ed2ce15a2330b91ab`; and
2. the deterministic student overlay produced below.

```bash
bundle_root="$(mktemp -d)"
.venv/bin/python labs/07_small_sar_codelab/scripts/make_student_bundle.py \
  --output "$bundle_root/trace-small-sar-student.zip"
```

The overlay contains the guided README, starter, runtime, four-case fixture,
preflight, and student tests. It excludes the solution, this guide, video
production files, and all scenario/geography data.

Do not distribute the full instructor branch if revealing the reference
solution matters. Students extract the overlay at the root of the supplied base
checkout.

## Instructor verification

Run:

```bash
TRACE_SMALL_SAR_CONTROLLER=solution .venv/bin/python -m pytest -q \
  labs/07_small_sar_codelab/tests
.venv/bin/python labs/07_small_sar_codelab/lab_runtime.py \
  --controller solution --case all
```

Expected decision summary:

```text
1. Welfare check
   TRACE: CLEAR - continue to the resource check
   Controller: ALLOCATE RES-ENGINE-01

2. Levee inspection
   TRACE: HOLD - stop before checking resources
   Controller: REFUSE

3. Medical response
   TRACE: CLEAR - continue to the resource check
   Controller: REFUSE

4. New information about the welfare check
   History: keep allocation v2, then append repair v4
```

Before distribution, have someone who did not author the lab complete the
student route without the solution. Record setup time, total time, every unclear
term, every skipped transition, and whether the person can explain TRACE versus
the controller without reading the README. This human walkthrough is a release
gate, not a replaceable automated test.

## Room triage

Use three cards or a shared poll:

- **Setup:** preflight is not `READY`.
- **Code:** preflight is ready, but a TODO test fails.
- **Explain:** tests pass; the student is ready for a concept check or extension.

| Signal | Fast response |
|---|---|
| Python not found | Move the student to a prepared machine; do not troubleshoot package managers live |
| Required package missing | Rerun the complete locked install or replace the environment |
| Workshop-data fingerprint mismatch | Replace the checkout; do not edit supplied data |
| TODO error | Direct the student to the named TODO and its one focused test |
| Many tests fail | Check the repository-root directory and `TRACE_SMALL_SAR_CONTROLLER=starter` |
| Replay mismatch | Save the first error and switch to a clean checkout |
| Output already exists | Create a new private practice directory |
| Screen-reader difficulty | Use the text diagram and provide the JSON only if requested |

## Teaching notes for the four cases

### 1. Welfare check: allocation

TRACE says `CLEAR`. `RES-ENGINE-01` is available, reachable, on route `XNG-04`,
and capable of a welfare check. The controller allocates it. This is the only
case where both questions answer yes.

### 2. Levee inspection: information refusal

Explain a levee as a barrier that helps hold back floodwater. A suitable unit is
available, but TRACE says `HOLD` because the information-freshness check failed.
The unit must not be selected.

### 3. Medical response: capacity refusal

TRACE says `CLEAR`, but both suitable units are unavailable. This is the
strongest test that students have not coded `CLEAR` as allocation.

### 4. Welfare-check update: append repair

A later report belongs to the same situation and TRACE record chain. Version 4
adds a correction. Version 2 remains in history, and no second unit is reserved.
Repeat that repair refers to the record, not physical rescue work.

## Discussion prompts

1. Which component checks information, and which checks resources?
2. Why can the levee and medical calls both refuse for different reasons?
3. Why does a resource-ID tie-break make the controller easier to reproduce?
4. Why should version 4 be added after version 2 instead of replacing it?
5. What would you want the saved decision to explain during a later review?

## Early finishers

- Add and test two units with equal travel time.
- Add an unreachable unit and explain why it is rejected.
- Reverse the input resource order and confirm the output order is unchanged.
- Use `--json` to draw call ID → TRACE version → controller decision → selected
  resource for one case.

Keep extensions inside the lab directory.

## Accessibility and inclusion

- Send the README and starter before class.
- Keep terminal and editor text at least 20 pt during projection.
- Read every command, error, and expected result aloud.
- Use the text alternative instead of requiring Mermaid rendering.
- Allow pairs, but ask each student to explain one decision in their own words.
- Provide setup time without removing the conceptual walkthrough.
- Never require students to share full screens or personal file paths for help.

## No-network fallback

After initial provisioning, all required execution is offline. Keep:

- preprovisioned repository checkouts;
- preinstalled Python environments for every supported platform;
- the student overlay zip; and
- printed or locally hosted copies of the README.

Do not rely on a live package index, Git host, container registry, or video host
during class.

## Instructor-only scientific and security guardrails

These constraints protect the exercise but should not become the opening
student lecture:

- Do not introduce debate or regret code; they are separate workshop topics.
- Do not expose hidden truth or hidden lineage.
- Do not run development or protected validation roles.
- Do not edit Small policy, configuration, calibration, manifest, or saved run.
- Keep student outputs in private temporary directories.
- Keep the exercise described as a simulation for learning.
- Do not turn the resource what-if examples into research claims.

## End-of-session feedback

Collect only teaching feedback:

- anonymous completion count;
- setup issue categories;
- the term or transition students found least clear;
- the TODO that required the most help;
- one-sentence explanations of `CLEAR` versus allocation; and
- accessibility improvements for the next workshop.
