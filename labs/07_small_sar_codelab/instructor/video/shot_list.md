# Screen-Capture Shot List — Real Code-Along

This is a **screen tutorial**, not a slide presentation. Keep the title card to
five seconds or less. For the main cut, show the actual README, terminal, and
editor that students will use.

Use a clean extracted student workspace copied with the private
[`05_DEMO_REVEAL_WORKFLOW.md`](../05_DEMO_REVEAL_WORKFLOW.md). Its terminal
commands after every reveal must be exactly the commands students run. Record
each row as a separate take so a typing error, pause, or setup delay can be
replaced without rerecording the whole lesson.

| Time | Frame to capture | Presenter action | Exact thing students should see | Keep the lesson focused on |
|---:|---|---|---|---|
| 00:00–00:35 | README system diagram | Introduce the question while the path is on screen | Call → visible evidence → TRACE → controller → saved action | TRACE checks information readiness; the controller checks resource availability. |
| 00:35–01:10 | README Start here, workspace map, route table | Point to the one file and one command surface | `exercise/rescue_controller.py`; `python workshop.py ...` | Students know where to begin and what not to edit. |
| 01:10–01:45 | README setup block, then terminal | Run setup, activate, and check | `python3 setup_workshop.py`; `source .venv/bin/activate`; `python workshop.py check`; five PASS lines | The ZIP is self-contained; Windows uses the README equivalent. |
| 01:45–02:40 | Terminal | Run the complete scenario, then the supplied text walkthrough | `scenario`; `walkthrough`; 1 allocated, 2 refused, 1 repaired | The completed scenario is supplied; the three TODOs have not run yet. |
| 02:40–03:35 | Terminal walkthrough, README Step 3 only if needed | Pause on each printed outcome | Allocation; information refusal; capacity refusal; repair | CLEAR allows a resource check. It does not dispatch a unit. |
| 03:35–05:10 | Editor on TODO 1, pause card, same editor file after reveal, terminal | Explain the comments; give an attempt pause; reveal off screen; explain the filter and sort; test | `eligible_resources`, then `python workshop.py test 1` | Four eligibility checks and travel-time/resource-ID ordering. |
| 05:10–07:35 | Editor on TODO 2, README table briefly, pause card, same editor file after reveal, terminal | Explain the decision order; give an attempt pause; reveal off screen; test | `decide_rescue`, then `python workshop.py test 2` | Mismatched input is an error; HOLD and no capacity are normal refusals. |
| 07:35–09:00 | Editor on TODO 3, pause card, same editor file after reveal, terminal | Explain the repair conditions; give an attempt pause; reveal off screen; test | `apply_visible_repair`, then `python workshop.py test 3` | Version 2 remains; version 4 is appended; no second resource is selected. |
| 09:00–10:20 | Terminal | Run all tests and the student controller | `test all`; `run` | The printed decisions now come from the student's own code. |
| 10:20–11:15 | Terminal | Run the capacity comparison | `python workshop.py what-if` | Capacity can change the action while TRACE stays CLEAR. |
| 11:15–12:10 | Terminal | Run the saved-history replay | `python workshop.py replay`; `Replay: byte-identical.` | Deterministic replay checks the same saved decision history. |
| 12:10–13:25 | README completion checklist | State the four learning outcomes | Call → TRACE → controller → history | Close the lesson; do not introduce a new concept. |

## Exact recording layout

- Use a 1920×1080, 16:9 canvas at 30 fps.
- Use an editor and terminal at 20–24 pt. When showing code, use a split view:
  editor on the left or top, terminal on the right or bottom. Keep no more than
  one TODO visible at a time.
- Show the README for orientation only: Start here, setup, the route table, and
  the relevant TODO rule. Do not scroll through every section or narrate it
  word for word.
- Put an on-screen pause card before each reveal: “Pause and attempt TODO N.”
  Resume on the same student filename; never show a solution filename, reveal
  command, private path, or replacement workspace.
- Keep a still cursor on screen for one beat after each command returns so the
  audience can read the result.

## Recording-state checklist

Before the first take, prepare a disposable instructor demo copy with the
private reveal workflow. Its `exercise/rescue_controller.py` starts with the
three student TODOs. Run the student setup once in that copy, then capture:

```bash
python workshop.py scenario
python workshop.py walkthrough
```

For each TODO take: show the starter comments, stop projection while the
private tool reveals that one function, return to the same filename, and run
the matching focused test. After TODO 3, capture:

```bash
python workshop.py test all
python workshop.py run
python workshop.py what-if
python workshop.py replay
```

Do not switch to a solution file, a hidden artifact, a second repository, or a
different command surface during the recording.

## Optional research-context postscript — not part of the core tutorial

Do not include this in the student code-along by default. If Dr. Chang asks for
it after reviewing the main cut, capture a separate 30–45 second postscript of
the larger TRACE Flood-SAR workbench. Label it on screen:

```text
Separate research-workbench context — not required for this student exercise
```

State that it uses a different dynamic scenario and does not run the student's
three functions. Do not require students to install it, and do not use it to
make learned-model or operational-response claims.
