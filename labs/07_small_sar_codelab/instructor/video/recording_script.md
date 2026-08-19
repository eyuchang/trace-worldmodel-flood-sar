# Recording Script: Build a Flood Rescue Controller by Coding It

Target main-cut length: **13 minutes 25 seconds**. This is a narrated,
screen-recorded code-along for students with no prior SAR or TRACE background.
It follows the student README in the same order, using an extracted student
workspace—not slides, the research repository, or a separate solution folder.

The presenter records only their screen and voice; no camera is needed. Use the
exact screen sequence in [`shot_list.md`](shot_list.md). The generated review
draft is a silent visual preflight, not the final tutorial.

## 00:00–00:35 — Start with what students will build

**Screen:** README system diagram.

**Narration:**

> A welfare-check call arrives during a simulated flood. We have information
> about the call, but we also have limited response units. In this lesson, you
> will write the controller that decides whether to allocate a suitable unit,
> refuse with a reason, or later append a correction. SAR means search and
> rescue: helping people during an emergency.

Point to the path. Say that TRACE is the decision notebook: it checks whether
the visible information is ready to use. The controller checks whether a
suitable response unit is actually available.

## 00:35–01:10 — Find the only file to edit

**Screen:** README “Start here,” workspace map, and seven-step route.

**Narration:**

> This README is your route map. You will edit exactly one file,
> `exercise/rescue_controller.py`, and run every workshop action with
> `python workshop.py`. First we will run the supplied scenario. Then you
> will complete three focused functions, test each one, and run the resulting
> controller.

Do not read the entire README aloud. Point to “Before Step 1” and say that it
contains the complete Windows, macOS, and Linux setup help.

## 01:10–01:45 — Set up this laptop, then confirm it is ready

**Screen:** README’s macOS/Linux setup block, then terminal. Keep the Windows
block visible long enough to say it is an equivalent alternative.

**Commands on macOS/Linux:**

```bash
python3 setup_workshop.py
source .venv/bin/activate
python workshop.py check
```

**Narration:**

> The ZIP contains everything this workshop needs. The setup command creates a
> private Python environment in this folder; it does not install packages,
> download a model, or require a GPU. Windows students use the PowerShell block
> in the README. After activation, everyone uses the same `python workshop.py`
> commands. Five PASS lines and READY mean you can continue.

Read the five labels once: Python, workshop files, teaching data, tests, and
workspace. Do not show a package manager or an unrelated terminal history.

## 01:45–02:40 — See the supplied complete system before coding

**Screen:** terminal.

**Commands:**

```bash
python workshop.py scenario
python workshop.py walkthrough
```

**Narration:**

> The scenario command runs a supplied completed flood session. It does not
> call the three unfinished functions we are about to write. The saved path is
> call, evidence, TRACE record, controller decision, commitment, and outcome.
> The walkthrough then zooms in on four completed decisions.

Point out the scenario count: one allocation, two refusals, and one repair.
These are controller events in a small teaching scenario.

## 02:40–03:35 — Read the four completed examples

**Screen:** terminal walkthrough output, with README Step 3 beside it only if
needed.

**Narration:**

> First, TRACE says CLEAR and a suitable engine is available, so the controller
> allocates it. Second, the levee-inspection information is on HOLD, so the
> controller refuses before checking resources. A levee is a barrier that helps
> hold back floodwater. Third, a medical response is CLEAR, but suitable units
> are busy, so the controller refuses for capacity. Finally, later visible
> evidence appends a repair: it keeps the version-two allocation and adds
> version four. It does not reserve another unit.

End with: “CLEAR allows the resource check. It does not mean a unit was sent.”

## 03:35–05:10 — TODO 1: choose eligible units

**Screen:** `exercise/rescue_controller.py` at `eligible_resources`.

**Narration before the pause:**

> A resource is a response unit. Keep it only when it is available, can reach
> the route, matches the requested route, and has the required capability. Then
> sort usable units by travel time and resource ID so the result is repeatable.
> Pause here and attempt TODO 1.

**Recording cut:** stop projection or insert a clear “try TODO 1 now” pause
card. In the disposable instructor demo copy, use the private reveal workflow
off screen. Return to the **same**
`exercise/rescue_controller.py` filename now showing the completed function.
Do not show a solution file or the reveal tool.

**Explain after the cut:** identify the four `and` conditions, the sort key,
and the `tuple(...)` return. Then run:

```bash
python workshop.py test 1
```

Say: “An empty tuple is normal when no unit qualifies.”

## 05:10–07:35 — TODO 2: allocate or refuse

**Screen:** `decide_rescue`, with the README decision table briefly visible
when introducing the branch order.

**Narration before the pause:**

> First make sure the request and TRACE authorization describe the same call
> and situation. A mismatch is invalid input, so raise `ValueError`. After
> that, TRACE comes before capacity. HOLD produces an information refusal.
> CLEAR allows us to check units. No eligible unit produces a capacity refusal;
> otherwise allocate the first eligible unit. Pause here and attempt TODO 2.

**Recording cut:** reveal TODO 2 off screen in the same instructor demo file.
Return to that exact filename. Walk through the two consistency checks, the
TRACE branch, the capacity branch, and the allocation branch. Then run:

```bash
python workshop.py test 2
```

Say: “HOLD and no capacity are normal refusal outcomes. They are not errors.”

## 07:35–09:00 — TODO 3: append a repair

**Screen:** `apply_visible_repair`.

**Narration before the pause:**

> A repair is a correction to the decision record, not physical repair work.
> It can extend history only when there is a prior decision, the belief cluster
> and TRACE record chain match, the version is later, and visible evidence
> supports the update. Each failed consistency check raises `ValueError`.
> Pause here and attempt TODO 3.

**Recording cut:** reveal TODO 3 off screen in the same instructor demo file.
Return to the exact same filename. Point to the five validations and the final
`return (*history, repair)`, then run:

```bash
python workshop.py test 3
```

Say: “The original allocation stays first.”

## 09:00–10:20 — Test and run the completed controller

**Screen:** terminal.

**Commands:**

```bash
python workshop.py test all
python workshop.py run
```

**Narration:**

> All twelve tests are now passing. The run applies your three functions to the
> four teaching cases. The terminal now prints decisions returned by your code,
> not the supplied walkthrough. Compare the output: one allocation, two
> different refusals, and one appended repair.

## 10:20–11:15 — Change capacity without changing TRACE

**Screen:** terminal.

**Command:**

```bash
python workshop.py what-if
```

**Narration:**

> These two runs change only copied resource snapshots. When welfare-check
> units become busy, the controller refuses. When a medical unit becomes
> available, the controller allocates it. TRACE stays CLEAR in both examples.
> That is why CLEAR is not the same as allocation.

## 11:15–12:10 — Replay the saved history

**Screen:** terminal.

**Command:**

```bash
python workshop.py replay
```

**Narration:**

> Replay regenerates the saved teaching history. Byte-identical means every
> saved file matches exactly. It lets us inspect the same decision path again
> rather than treating a rerun as a new result.

## 12:10–13:25 — Close the loop

**Screen:** README completion checklist, then terminal replay result.

**Narration:**

> You built the bridge from information to action. A call produced visible
> evidence. TRACE decided whether that evidence could reach the resource check.
> Your controller allocated a suitable unit or refused with a reason. Later
> evidence appended a repair without erasing the earlier decision. Use the
> README checklist to finish, reset your practice files if needed, and keep
> experimenting only inside the exercise and tests folders.

## Optional postscript only when requested by Dr. Chang

The larger TRACE Flood-SAR research workbench may be shown for 30–45 seconds
after the main cut, using the warning card specified in
[`shot_list.md`](shot_list.md). It is not part of the setup, code, or
execution tutorial and must not be presented as the student package or as
evidence of operational readiness.
