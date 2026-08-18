# Full Lesson Run of Show — 3 Hours 15 Minutes

Use this document during the full workshop. Complete
[`01_PREP_AND_DISTRIBUTION.md`](01_PREP_AND_DISTRIBUTION.md) before class and
keep [`04_LIVE_QUICK_REFERENCE.md`](04_LIVE_QUICK_REFERENCE.md) open for room
triage.

Private answer reference: the complete implementations of all three TODOs are
in [`solution/rescue_controller.py`](solution/rescue_controller.py).

The teaching job is not to explain all of TRACE. It is to help first-time
students build one accurate mental model:

```text
TRACE asks: Is the information ready to use?
The controller asks: Is a suitable response unit available?
```

## Schedule at a glance

| Time | Student location | Slides | Move-on result |
|---:|---|---:|---|
| 0:00–0:20 | Start here and system explanation | 1–4 | Students can distinguish TRACE from the controller |
| 0:20–0:30 | Step 1 | 5 | Everyone sees five PASS lines |
| 0:30–0:45 | Step 2 | 6 | Students can read the call-to-outcome path |
| 0:45–1:10 | Step 3 | 7 | Students distinguish the two refusal reasons |
| 1:10–1:20 | Break | — | Helpers clear setup issues |
| 1:20–1:50 | Step 4, TODO 1 | 8 | One eligibility test passes |
| 1:50–2:25 | Step 4, TODO 2 | 9 | Five allocation/refusal tests pass |
| 2:25–2:50 | Step 4, TODO 3 | 10 | Two repair tests pass |
| 2:50–3:00 | Step 5 | 11 | All eight tests and full controller run pass |
| 3:00–3:10 | Step 6 | 12 | Students explain the capacity comparison |
| 3:10–3:15 | Step 7 | 13 | Both replay checks are byte-identical |

## Opening — Mission and system

**Time:** 0:00–0:20
**Student README:** “Start here” through “Words you will use”
**Slides:** 1–4

### Teaching objective

Students should understand what they are building before seeing a terminal.

### Say and show

Begin with the welfare-check story:

> A call arrives during a flood. The information may be ready to use, and a
> response unit may be available. What must the software check before it sends
> that unit?

Reveal the path one step at a time:

```text
call -> visible evidence -> TRACE -> controller -> allocation or refusal
                               later information -> append a repair
```

Use “hidden answer key” only to establish that the controller does not know the
simulation's complete story. Then return immediately to the visible path.

Say the two questions aloud:

> TRACE checks whether the information is ready. Your controller checks whether
> a suitable unit is available. CLEAR permits the second check; it does not send
> a unit.

### Students do

Students read the workspace map and point to:

- the one file they edit;
- the one command runner; and
- the support folder they can ignore.

### Ask

1. “What question has TRACE answered?”
2. “What question remains before a unit can be selected?”
3. “Can the controller read the hidden answer key?”

### Move on when

Several students can answer all three without reading the slide. Do not start
setup while the room still equates `CLEAR` with allocation.

### Likely misconception and recovery

If a student says “TRACE dispatches the unit,” point to the gap between TRACE
and the controller in the diagram and ask what resource information has not yet
been checked.

## Step 1 — Check setup

**Time:** 0:20–0:30
**Student README:** Step 1
**Slide:** 5

### Teaching objective

Move the entire room to one known starting state without live package repair.

### Say and show

Run the same command students will run:

```bash
python workshop.py check
```

Read the five labels aloud: Python, workshop files, packages, examples, and
workspace.

### Students do

Run the command and select the **Setup** status only if they do not see `READY`.

### Expected screen result

Five `PASS` lines followed by:

```text
READY: continue to Step 2 with 'python workshop.py scenario'.
```

### Move on when

At least 95% of the room is ready and every remaining setup issue is assigned
to a helper. Move affected students to a prepared machine; do not turn this
segment into a package-manager lesson.

## Step 2 — Preview the complete scenario

**Time:** 0:30–0:45
**Student README:** Step 2
**Slide:** 6

### Teaching objective

Connect the small coding exercise to an actual deterministic Small run.

### Say and show

Tell students that this command runs the supplied completed TRACE Small
scenario, not their unfinished exercise functions. They will later implement
the bounded controller rules for four representative decisions; they are not
rebuilding the full scenario system.

```bash
python workshop.py scenario
```

Focus only on:

```text
8 allocated, 12 refused, 8 repaired
```

Then show the six saved filenames and read them as a sentence from call to
outcome. Do not open hidden files or spend time on simulator diagnostics.

### Students do

Run the scenario and locate the printed decision path.

### Ask

“Which saved file comes immediately before a commitment?”

### Move on when

Students can say that the counts describe controller events and can read the
six-file sequence in order.

### Likely misconception and recovery

If students interpret all 28 events as separate people or casualties, return
to the wording “controller events.” The lesson does not make a casualty claim.

## Step 3 — Four completed decisions

**Time:** 0:45–1:10
**Student README:** Step 3
**Slide:** 7

### Teaching objective

Make the decision table intuitive before asking students to encode it.

### Say and show

```bash
python workshop.py walkthrough
```

Teach one contrast at a time:

1. **Welfare check:** information ready + eligible unit → allocate.
2. **Levee inspection:** information not ready → refuse before resource check.
3. **Medical response:** information ready + no eligible unit → capacity refusal.
4. **Later report:** keep version 2 + append repair version 4.

Define a levee as a barrier that helps hold back floodwater. Define repair as a
record correction, not physical repair work.

### Students do

Annotate the two questions beside each case:

```text
Information ready?  yes/no
Eligible unit?      yes/no/not checked
```

### Ask

1. “Why do Cases 2 and 3 both refuse?”
2. “Why is resource availability irrelevant in Case 2?”
3. “What remains in history after version 4 arrives?”

### Move on when

Students can explain the two refusal reasons and say that version 2 remains.

## Break

**Time:** 1:10–1:20

Keep helpers available for setup recovery. Ask ready students to open
`exercise/rescue_controller.py` but not begin TODO 2 before TODO 1.

## Step 4A — TODO 1: eligible resources

**Time:** 1:20–1:50
**Student README:** Step 4, TODO 1
**Slide:** 8

### Teaching objective

Translate four plain resource rules into a deterministic filter and sort.

### Say and show

Open the student exercise, not the solution. Point out that the comments give
three implementation steps and that `_decision_from_trace` is already complete
for later TODOs.

Walk through the four yes/no resource fields. Explain the tuple used for
sorting:

```text
(routed_travel_s, resource_id)
```

### Students do

Implement only `eligible_resources`, then run:

```bash
python workshop.py test 1
```

### Ask

“If two units have the same travel time, what makes their order repeatable?”

### Move on when

The eligibility test passes. Students who finish early should add a wrong-route
unit on paper and predict whether it remains.

### Likely misconception and recovery

If a student uses `or` between the four rules, ask whether a busy but reachable
unit should be eligible. Let the example reveal why all four conditions must
hold.

## Step 4B — TODO 2: allocate or refuse

**Time:** 1:50–2:25
**Student README:** Step 4, TODO 2
**Slide:** 9

### Teaching objective

Encode the TRACE/resource boundary in the correct order.

### Say and show

Display the three-row decision table from the README. Emphasize that the
function should call `eligible_resources` once and use the supplied helper for
every returned decision.

Order matters:

1. verify the request and authorization refer to the same call and situation;
2. refuse immediately unless TRACE is `CLEAR`;
3. check eligible units;
4. refuse if none; otherwise allocate the first.

### Students do

Implement `decide_rescue`, then run:

```bash
python workshop.py test 2
```

### Ask

“Which line guarantees that a visible unit cannot override a TRACE hold?”

### Move on when

All five allocation/refusal tests pass and students can identify the
information-refusal branch and capacity-refusal branch in their code.

### Likely misconception and recovery

If a student checks resources before TRACE, return to the system diagram and
ask whether the resource question is permitted when information is on hold.

## Step 4C — TODO 3: append a repair

**Time:** 2:25–2:50
**Student README:** Step 4, TODO 3
**Slide:** 10

### Teaching objective

Preserve history while adding a later evidence-supported correction.

### Say and show

Use the version timeline in the README. Point to `history[-1]` as the most
recent earlier decision. Explain each comparison in story language: same
situation, same record chain, later version, visible support.

### Students do

Implement `apply_visible_repair`, then run:

```bash
python workshop.py test 3
```

### Ask

“What would be lost if version 4 replaced version 2?”

### Move on when

Both repair tests pass, version 2 remains first, and the repair has no selected
resource.

## Step 5 — Complete tests and controller run

**Time:** 2:50–3:00
**Student README:** Step 5
**Slide:** 11

### Students do

```bash
python workshop.py test all
python workshop.py run
```

### Expected screen result

Eight tests pass. The exercise controller then produces the same four decisions
as the supplied walkthrough.

### Move on when

Students can point from each visible output reason to the branch that created
it. Use the **Code** room status for remaining test failures.

## Step 6 — Capacity comparison

**Time:** 3:00–3:10
**Student README:** Step 6
**Slide:** 12

### Students do

```bash
python workshop.py what-if
```

### Ask

“What stayed the same, and what changed?”

### Move on when

Students answer: TRACE stayed `CLEAR`; resource capacity changed; therefore the
controller action changed.

## Step 7 — Replay the saved histories

**Time:** 3:10–3:15
**Student README:** Step 7
**Slide:** 13

### Students do

```bash
python workshop.py replay
```

### Expected screen result

Both the fresh replay and saved class replay are byte-identical.

### Close

End on the successful replay result and restate the practical distinction:
TRACE permits the resource check; the controller still needs eligible capacity
before it can allocate a unit. No additional student response is required.
