# Recording Script: Should We Send a Flood-Response Unit?

Target length: **14:50**. This is the complete narration and screen sequence
for students who have never studied search and rescue or TRACE.

The checked-in review video is silent and uses condensed timed captions. A
human presenter can read this script without inventing definitions, commands,
or transitions.

## 00:00–00:35 — The mission

**Screen:** Minimal title card: “A flood call arrives. Should we send a unit?”
Subtitle: “Build the controller that makes and explains the decision.”

**Narration:**

Imagine you are helping a flood-response team. A call asks for a welfare check:
someone may need help, and a response unit might be able to reach them. Should
the software send that unit? In this lab, you will program that decision. You
do not need any previous search-and-rescue or TRACE experience.

## 00:35–01:40 — How a call becomes a decision

**Screen:** Reveal five steps, one at a time: call, evidence, TRACE, your
controller, recorded action.

**Narration:**

Search and rescue, shortened to SAR, is the work of finding, reaching, and
helping people during an emergency. Our simulated team receives calls but has
limited response units. Each call produces evidence: information the software
is allowed to use. Because this is a simulation, it also has a hidden answer
key describing the complete made-up situation. The controller cannot read that
answer key; it must decide from the visible evidence. TRACE records what the
system believes from that evidence and whether the proposed action may move
forward. Then your controller checks the units. It either selects one or
refuses with a reason. The result is saved so someone can later understand what
happened.

## 01:40–02:50 — TRACE and the controller answer different questions

**Screen:** Two large questions:

```text
TRACE: Is the information ready to use?
YOU:   Is a suitable unit available?
```

Then reveal `CLEAR` and `HOLD`.

**Narration:**

Think of TRACE as the system's decision notebook. It stores a versioned record
of a proposal and its supporting evidence. In this lab, CLEAR means the
proposal passed the information checks, so your controller may continue to the
resource check. HOLD means the information is not ready to use, perhaps because
it is too old. A hold stops the controller before it selects a unit. The key
idea is simple: CLEAR allows the next check. CLEAR does not dispatch anything.

## 02:50–03:55 — The three outcomes students will code

**Screen:** Three plain-language outcomes: allocate, refuse, repair.

**Narration:**

Your controller records three kinds of event. An allocation selects a suitable
unit. A commitment then reserves that unit for the request. A refusal selects
no unit and records why: either TRACE did not clear the information, or no
suitable unit was available. A repair is different. It is not a crew fixing a
physical object. It is a later correction added to the decision history when
new information arrives. The earlier decision stays visible.

## 03:55–04:50 — Check the setup

**Screen:** Clean terminal with a generic prompt.

**Command:**

```bash
python workshop.py check
```

**Expected ending:**

```text
[PASS] examples: four rescue examples are ready
[PASS] workspace: practice output is writable
READY: continue to Step 2 with 'python workshop.py scenario'.
```

**Narration:**

The check command verifies your Python version, the workshop files, the required Python
packages, the four rescue examples, and a private place for practice output. If
you see five PASS lines and READY, continue. If a check fails, share that one
line with an instructor instead of trying to change the supplied data.

## 04:50–06:00 — Run the flood scenario

**Screen:** Run the command, highlight the counts, and reveal the saved path.

**Commands:**

```bash
python workshop.py scenario
```

**Expected highlights:**

```text
Scenario complete: 8 allocated, 12 refused, 8 repaired.
call -> evidence -> TRACE record -> controller decision -> commitment -> outcome
```

**Narration:**

A scenario is one complete simulated flood-response session. This run records
eight allocations, twelve refusals, and eight later repairs. It also saves the
public path from a call and visible evidence through the TRACE record,
controller decision, commitment, and outcome. You will replay the run after
your controller is complete.

## 06:00–07:35 — Walk through four completed cases

**Screen:** Run the walkthrough. Reveal one case at a time and keep the final
key idea visible.

**Command:**

```bash
python workshop.py walkthrough
```

**Narration:**

The first call requests a welfare check. TRACE says CLEAR, Engine 01 is usable,
and the controller allocates it. The second asks for a levee inspection. A
levee is a barrier that helps hold back floodwater. A unit exists, but TRACE
says HOLD because the information is too old, so the controller refuses. The
third is a medical response. TRACE says CLEAR, but both suitable units are busy,
so the controller refuses for lack of capacity. Finally, new information about
the welfare check produces record version four. The system keeps the allocation
at version two and appends a repair. It does not reserve a second unit.

## 07:35–08:50 — TODO 1: which units can help?

**Screen:** Show the two welfare-check resources and the four eligibility
questions beside `eligible_resources`.

**Narration:**

Your first function reads the dispatch board. A resource is a response unit. A
capability is a task that unit can perform, such as a welfare check. Keep a unit
only if it is currently available, its route is reachable, its route matches the
request, and it has the required capability. Then sort usable units by travel
time and resource ID. The ID breaks a tie, which makes the result deterministic:
the same input always produces the same order.

**Test:**

```bash
python workshop.py test 1
```

## 08:50–10:20 — TODO 2: should we send one?

**Screen:** Decision table:

| TRACE | Eligible unit? | Controller result |
|---|---|---|
| not CLEAR | either | refuse: information |
| CLEAR | no | refuse: capacity |
| CLEAR | yes | allocate first unit |

**Narration:**

Your second function joins the two decisions. First, confirm that the request
and TRACE authorization refer to the same call and situation. The call ID names
one report. The belief-cluster ID groups reports that the system believes are
about the same situation. If TRACE is not CLEAR, refuse before checking units.
With CLEAR, call your resource filter. An empty result means capacity refusal.
Otherwise allocate the first eligible unit. The exercise already provides a
helper that copies the shared TRACE record fields; focus on the decision order
rather than repetitive setup code.

**Test:**

```bash
python workshop.py test 2
```

## 10:20–11:35 — TODO 3: new information, same history

**Screen:** Timeline with both versions still visible:

```text
version 2: allocation stays in history
version 4: repair is appended
```

**Narration:**

Your third function receives an existing history and a later TRACE record. The
history is a Python tuple: an ordered sequence this lab treats as immutable.
Require an earlier decision, the same situation group, the same TRACE record
chain, a larger version number, and a nonempty list of visible evidence behind
the update. Return the old history plus one repair. Do not replace version two,
select Engine 01 again, or create a second commitment.

**Test:**

```bash
python workshop.py test 3
```

## 11:35–12:50 — Test and run the finished controller

**Screen:** Show the full green test summary, then the friendly four-case
walkthrough produced by the exercise controller.

**Commands:**

```bash
python workshop.py test all
python workshop.py run
```

**Narration:**

Run every student test. A failure name points to the rule that still needs
work. When the suite is green, run your controller on all four cases. Your
output should match the completed walkthrough: welfare-check allocation,
information refusal, capacity refusal, and an appended repair. The workshop
runtime supplies the calls, TRACE decisions, and resource snapshots. The three
functions you wrote supply the final controller decisions.

## 12:50–13:55 — Change capacity and watch the result

**Screen:** Show the two commands followed by their changed decisions.

**Commands:**

```bash
python workshop.py what-if
```

**Narration:**

These two what-if runs change only copied resource snapshots. First, make the
welfare-check units busy. TRACE still says CLEAR, but the controller now
refuses. Next, make a medical-response unit available. TRACE still says CLEAR,
and the controller now allocates it. This isolates the lesson: changing
capacity can change the controller decision even when TRACE stays the same.

## 13:55–14:50 — What you built

**Screen:** Run replay, then reveal the final learning checklist.

**Command:**

```bash
python workshop.py replay
```

**Narration:**

You built the bridge between information and action. A call produced evidence.
TRACE decided whether that evidence could move forward. Your code checked the
response units, made an allocation or one of two refusals, and preserved history
when new information arrived. You also tested how capacity changes the outcome.
The final replay regenerates both your fresh run and the saved class example;
byte-identical means every saved file matches. The README ends with a completion
checklist, troubleshooting, reset instructions, and optional challenges.

## Final on-screen checklist

Keep this card visible through the end:

> I can explain the path from a flood call to a controller decision.
> I can explain why CLEAR is not the same as allocation.
> I can explain information refusal versus capacity refusal.
> I can append a repair without erasing the earlier decision.
> This workshop uses a simulation for learning.
