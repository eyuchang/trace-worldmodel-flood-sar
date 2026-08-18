# Flood Rescue Controller Workshop

## Start here

A welfare-check call arrives during a simulated flood. The information may be
ready to use—but should the system actually send a response unit?

That is the decision you will program.

You will build a small controller that can:

1. allocate a suitable response unit;
2. refuse because the information is not ready;
3. refuse because no suitable unit is available; and
4. append a later correction without erasing the earlier decision.

No search-and-rescue or TRACE background is required. The full workshop takes
about **2.5–4 hours**.

> **Edit only:** `exercise/rescue_controller.py`
>
> **Run everything through:** `python workshop.py ...`

## Your workspace

```text
trace-small-sar-workshop/
├── README.md                         follow this lesson from top to bottom
├── workshop.py                       run workshop commands
├── exercise/
│   └── rescue_controller.py          the only file you edit
├── tests/
│   └── test_rescue_controller.py     readable checks for your three TODOs
└── _support/                          supplied examples and runtime; do not edit
```

You do not need to explore the larger TRACE research repository.

Run this at any time to see the workshop route:

python workshop.py

## What system are you building?

**Search and rescue (SAR)** is the work of finding, reaching, and helping people
during an emergency. A response team has limited units—such as engines, boats,
or medical teams—so software must answer two different questions:

1. Is the available information ready to use?
2. If it is, is a suitable response unit actually available?

TRACE—the system's **decision notebook**—answers the first question. **Your
controller answers the second.**

```mermaid
flowchart LR
    A["Flood call"] --> B["Visible evidence"]
    B --> C["TRACE: may the action move forward?"]
    C --> D["Your controller: is a suitable unit available?"]
    D --> E["Allocate a unit"]
    D --> F["Refuse with a reason"]
    G["Later information"] --> H["Append a repair"]
    H --> D
```

**Text alternative:** a call produces evidence the controller is allowed to
see. TRACE decides whether that information may move forward. Your controller
then checks the response units and either allocates one or refuses with a
reason. Later information can append a repair without deleting the earlier
history.

### Visible evidence—not the answer key

The simulation creates a complete story of what is happening. Think of that
story as a **hidden answer key**. The controller cannot read it.

The controller receives only **visible evidence**: the partial information
revealed by calls and observations. TRACE records what the system currently
believes from that evidence. This makes the exercise realistic in one important
way: the controller must decide from the information it has, not from the
simulation's answer key.

### TRACE decisions in this workshop

- **CLEAR:** the information checks passed. Your controller may continue to
  the resource check. CLEAR does **not** send a unit.
- **HOLD:** the information is not ready to use. Your controller stops before
  choosing a unit.

### Words you will use

| Term | Meaning here |
|---|---|
| **Call** | A request for help, such as a welfare check |
| **Evidence** | Information the controller is allowed to use |
| **Controller** | Your code that combines TRACE's decision with resource availability |
| **Resource** | A response unit with a route, capabilities, and availability state |
| **Eligible resource** | A unit that is available, reachable, on the requested route, and capable of the task |
| **Capacity** | At least one eligible resource is free |
| **Allocation** | Selecting a resource for the request |
| **Commitment** | Reserving the selected resource for that request |
| **Refusal** | Selecting no resource and recording why |
| **Repair** | A later correction to the decision record—not a physical repair |
| **Replay** | Running the same scenario again and checking that every saved file matches |

## Your seven-step route

| Step | What you do | Approximate time |
|---:|---|---:|
| 1 | Check the prepared environment | 5–15 minutes |
| 2 | Preview the supplied complete scenario | 15 minutes |
| 3 | Study four completed decisions | 20–25 minutes |
| 4 | Implement and test three functions | 90–120 minutes |
| 5 | Run your completed controller | 15 minutes |
| 6 | Change resource capacity | 15–20 minutes |
| 7 | Replay the saved histories | 15 minutes |

---

## Step 1 — Check your setup

**GOAL:** confirm that Python, the workshop files, the four examples, and your
practice-output directory are ready.

**DO THIS:** open a terminal in this workshop folder and run:

```bash
python workshop.py check
```

**EXPECTED:**

```text
[PASS] python: Python 3.11 is ready
[PASS] workshop-files: guide, exercise, tests, and examples found
[PASS] packages: required Python packages are available
[PASS] examples: four rescue examples are ready
[PASS] workspace: practice output is writable
READY: continue to Step 2 with 'python workshop.py scenario'.
```

Python 3.12 is also supported, so the first line may say `Python 3.12`.

**READY SIGNAL:** you see five `PASS` lines and `READY`. If you see `STOP`,
share that one line with an instructor rather than changing the supplied files.

---

## Step 2 — Preview the complete flood scenario

Before you write the controller, preview the larger system it will join. This
command runs a **supplied, already-completed TRACE Small flood scenario**. It
does not call the three unfinished functions in your exercise file.

Think of this run as an end-to-end example. It shows how a simulated call moves
through evidence, TRACE, a completed controller, a resource commitment, and an
outcome. In Step 4, you will implement the bounded controller rules for four
representative decisions from this larger scenario; you are not expected to
rebuild the rest of TRACE.

Run the supplied scenario:

```bash
python workshop.py scenario
```

You should see:

```text
Scenario complete: 8 allocated, 12 refused, 8 repaired.
Saved decision path:
  call -> evidence -> TRACE record -> controller decision -> commitment -> outcome
```

Read the counts as recorded controller events:

- `8 allocated`: eight requests received a resource commitment;
- `12 refused`: twelve requests received no resource; and
- `8 repaired`: eight histories received a later correction.

The run creates a hidden `.workshop/run` directory. You do not need to browse
all of it. These six files form the path you are studying:

```text
calls.json
evidence_ledger.json
trace_records.json
controller_decisions.json
commitments.json
outcomes.json
```

An **evidence ledger** is the saved log of evidence entries. For now, the
important idea is the order of the six files, not their internal JSON details.

---

## Step 3 — Study four completed controller decisions

Now zoom in on four representative decisions from the supplied scenario. They
show the three kinds of result a controller can record for a rescue request or
later update: an **allocation**, a **refusal**, or an appended **repair**. Your
three exercise functions will implement the rules that produce these results.

Run the walkthrough:

```bash
python workshop.py walkthrough
```

The command uses the supplied completed decisions so you can see the target
behavior without revealing the exercise solution.

### Case 1: welfare check → allocate

TRACE says `CLEAR`. Engine 01 is available, can reach the route, is assigned to
that route, and can perform a welfare check. The controller allocates it.

```text
TRACE: CLEAR
Controller: ALLOCATE RES-ENGINE-01
```

### Case 2: levee inspection → information refusal

A **levee** is a barrier that helps hold back floodwater. A suitable unit is
available, but the evidence is too old. TRACE says `HOLD`, so the controller
stops before checking resources.

```text
TRACE: HOLD
Controller: REFUSE
Why: TRACE did not clear the action
```

### Case 3: medical response → capacity refusal

TRACE says `CLEAR`, but both suitable units are busy. The controller refuses
because no eligible resource is available.

```text
TRACE: CLEAR
Controller: REFUSE
Why: no suitable unit is currently available
```

This is the central differentiator:

```text
CLEAR means “you may check resources.”
CLEAR does not mean “a resource was sent.”
```

### Case 4: later information → append a repair

Later visible evidence updates the welfare-check record from version 2 to
version 4. The controller keeps the earlier allocation and appends a repair. It
does not reserve a second unit.

```text
History: keep allocation v2, then append repair v4
New resource commitment: no
```

Before coding, notice the key contrast: Case 2 refuses because TRACE has not
cleared the information, while Case 3 reaches the resource check but finds no
eligible unit. Case 4 adds new history instead of replacing version 2.

---

## Step 4 — Build and test the controller

**GOAL:** implement the three small decisions that connect TRACE, resource
availability, and later record updates.

Open the only file you will edit:

```text
exercise/rescue_controller.py
```

It contains exactly three TODO functions. Complete them in order.

### Meet the inputs

| Type | What it gives your function |
|---|---|
| `RescueRequest` | The call, requested task, required capability, and route |
| `TraceAuthorization` | TRACE's `CLEAR` or `HOLD` decision and record version |
| `ResourceView` | What the controller can currently see about one unit |
| `RescueDecision` | The allocation, refusal, or repair your function returns |

In `TraceAuthorization`, “authorization” means permission to continue to the
resource check. It does not mean that a unit was dispatched.

Two identifiers keep information attached to the correct situation:

- `call_id` identifies one call;
- `belief_cluster_id` groups calls believed to describe the same situation.

The workshop supplies these objects. You do not construct them yourself.

### TODO 1 — Which units can help?

Implement `eligible_resources`.

Keep a resource only when all four checks pass:

1. it is currently available;
2. its route is reachable;
3. its route matches the request; and
4. it has the required capability.

Sort the remaining resources by:

```text
(routed_travel_s, resource_id)
```

`routed_travel_s` is the estimated route travel time in seconds. The resource
ID breaks a tie. This makes the result **deterministic**: the same inputs always
produce the same order.

Test TODO 1:

```bash
python workshop.py test 1
```

**WHEN IT PASSES:** the command reports one passing test and tells you to start
TODO 2.

### TODO 2 — Should the controller send a unit?

Implement `decide_rescue` using this table:

| TRACE decision | Eligible unit? | Controller result |
|---|---:|---|
| anything other than `CLEAR` | either | refuse: information |
| `CLEAR` | no | refuse: capacity |
| `CLEAR` | yes | allocate the first eligible unit |

Apply the checks in this order:

1. confirm that the request and TRACE authorization have the same `call_id`
   and `belief_cluster_id`;
2. refuse with `TRACE_NOT_CLEAR` when TRACE is not `CLEAR`;
3. call your `eligible_resources` function;
4. refuse with `NO_COMPATIBLE_CAPACITY` when the result is empty; or
5. allocate the first result with `ALLOCATED_COMPATIBLE_CAPACITY`.

Use the imported `RescueDecision`, `RescueEventType`, and `ReasonCode` types.
Do not hard-code the welfare-check call or Engine 01.

Test TODO 2:

```bash
python workshop.py test 2
```

**WHEN IT PASSES:** all five allocation/refusal tests pass.

### TODO 3 — How should later information be recorded?

Implement `apply_visible_repair`.

Imagine the decision history as a timeline:

```text
version 2: allocate Engine 01
version 3: later information begins an update
version 4: append a repair
```

Require:

- at least one earlier decision;
- the same `belief_cluster_id`;
- the same TRACE `record_id`;
- a larger `record_version`; and
- a nonempty `visible_evidence_basis`—the visible information behind the
  update.

The history is a Python **tuple**, an ordered sequence this exercise treats as
unchangeable. Return the old tuple plus one new `REPAIR` event. Do not replace
the allocation or select the unit again.

Test TODO 3:

```bash
python workshop.py test 3
```

Then run all eight behavior tests:

```bash
python workshop.py test all
```

**WHEN ALL TESTS PASS:** the command tells you to run your
controller.

---

## Step 5 — Run your controller

Your three functions are now complete. Connect them to the four teaching cases
and compare their results with the supplied walkthrough from Step 3.

Run:

```bash
python workshop.py run
```

Your output should match the four decisions from Step 3:

- welfare check → allocate Engine 01;
- levee inspection → information refusal;
- medical response → capacity refusal; and
- later welfare-check evidence → append repair version 4.

This confirms that the functions you wrote reproduce the completed examples:
TRACE status separates information refusal from the resource check, capacity
separates allocation from capacity refusal, and the repair remains appended to
the earlier history.

---

## Step 6 — Change capacity

Next, change only resource availability and observe how your controller reacts
while TRACE stays the same.

Run:

```bash
python workshop.py what-if
```

The command asks two questions:

1. What if all welfare-check units become busy?
2. What if a medical-response unit becomes available?

In both examples, TRACE stays `CLEAR`. The first controller result changes from
allocation to capacity refusal. The second changes from capacity refusal to
allocation.

---

## Step 7 — Replay the saved histories

Finish by checking deterministic replay: the fresh run from Step 2 and the
saved class run should both regenerate exactly.

Run:

```bash
python workshop.py replay
```

You should see:

```text
Fresh replay: byte-identical.
Saved class replay: byte-identical.
COMPLETE: CLEAR permits a resource check; allocation also requires capacity.
```

“Byte-identical” means every saved file matches exactly. Deterministic replay
makes it possible to inspect the same decision history again.

```text
call -> visible evidence -> TRACE -> resource check -> saved action -> outcome
                                      |
                              later repair is appended
```

## Completion checklist

- [ ] The setup command reports five `PASS` lines and `READY`.
- [ ] All eight behavior tests pass.
- [ ] My controller produces the four expected decisions.
- [ ] The capacity comparison changes controller results while TRACE stays `CLEAR`.
- [ ] Both replay checks report `byte-identical`.

## Troubleshooting

| What you see | What to do |
|---|---|
| `python: command not found` | Ask an instructor to open the prepared workshop terminal |
| `STOP: The prepared TRACE Small runtime was not found` | Ask for the prepared environment; do not install a model |
| A TODO test fails | Read the first failure, then return to that TODO's decision rule |
| `NotImplementedError: TODO ...` | Complete that named function in `exercise/rescue_controller.py` |
| `run already exists` | Continue to the next step or reset if you intend to restart |
| Replay says to run Step 2 | Run `python workshop.py scenario` first |
| Many import errors | Confirm your terminal is open in the workshop folder |

## Reset practice outputs

To remove generated runs while keeping your controller code:

```bash
python workshop.py reset
```

The command removes only this workspace's hidden `.workshop` directory. It does
not change `exercise/rescue_controller.py`.

To reset your code, replace `exercise/rescue_controller.py` with a fresh copy
from the student package.

## Optional challenges

After the required route is complete, you may:

- add a test with two equal-travel-time units and confirm the resource-ID
  tie-break;
- add an unreachable unit and explain why it is rejected; or
- reverse the input resource order and confirm the selected order is unchanged.

Keep your changes inside `exercise/` and `tests/`.

## Accessibility

- The text below every diagram communicates the same information as the image.
- Every required action is available through a keyboard-run terminal command.
- Commands and expected outputs are presented as selectable text.
- Ask for a paired workflow or additional setup time if either would help.
