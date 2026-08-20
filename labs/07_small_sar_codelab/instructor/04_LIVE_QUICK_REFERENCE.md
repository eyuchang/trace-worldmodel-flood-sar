# Live Workshop Quick Reference

Keep this page open during either lesson. It contains commands, expected
signals, and room triage—not teaching narration.

Private answer reference:
[`solution/rescue_controller.py`](solution/rescue_controller.py) contains the
complete, tested implementation of all three student methods.

## Command sequence

| Stage | Command | Success signal |
|---|---|---|
| Local setup | Follow README’s macOS/Linux or Windows block | `.venv` activated; no package download |
| Menu | `python workshop.py` | Seven numbered steps |
| Setup | `python workshop.py check` | Five PASS lines and READY |
| Scenario | `python workshop.py scenario` | 1 allocated, 2 refused, 1 repaired |
| Walkthrough | `python workshop.py walkthrough` | Four explained decisions |
| TODO 1 | `python workshop.py test 1` | One test passes |
| TODO 2 | `python workshop.py test 2` | Five tests pass |
| TODO 3 | `python workshop.py test 3` | Six tests pass |
| All behavior | `python workshop.py test all` | Twelve tests pass |
| Student run | `python workshop.py run` | Same four decisions as walkthrough |
| Comparison | `python workshop.py what-if` | CLEAR remains; capacity/action changes |
| Replay | `python workshop.py replay` | One byte-identical replay message |
| Reset outputs | `python workshop.py reset` | Outputs removed; exercise kept |

## The three concepts to protect

```text
CLEAR permits a resource check; it does not dispatch a unit.
Information refusal and capacity refusal are different.
A repair appends history; it does not replace the earlier decision.
```

## Room-status system

- **Setup:** no READY line.
- **Code:** setup works, but a TODO test fails.
- **Explain:** tests pass; student wants a concept check or extension.

Route Setup issues to the setup lead. Route Code issues to table helpers. Dr.
Chang should keep teaching unless the same failure affects a substantial part
of the room.

## Fast triage

| Signal | Immediate response |
|---|---|
| `python: command not found` | Activate `.venv`, then run `python workshop.py check` |
| `python3` or `py` is not found | Follow the README’s official-Python installation link, then reopen the terminal |
| `SETUP STOP: Python ... is required` | Install Python 3.11–3.14, then rerun `setup_workshop.py` |
| `.venv already exists` | Use `setup_workshop.py --repair` only if the student agrees to replace that local environment |
| Workshop folder incomplete | Replace it with a fresh extracted ZIP |
| `NotImplementedError: TODO N` | Open the named function; do not edit support files |
| One TODO test fails | Read only the first failure and compare it with that TODO's rule list |
| Many import errors | Confirm terminal is in `trace-small-sar-workshop` |
| Output already exists | Continue, or reset only if the student intends to restart |
| Replay requires Step 2 | Run the scenario before replay |
| Screen-reader difficulty | Use the README text alternative and selectable outputs |

## TODO decision reminders

### TODO 1

Eligible means all four:

```text
available AND reachable AND correct route AND required capability
```

Sort by travel time, then resource ID.

### TODO 2

```text
same call and situation?
  no  -> ValueError
TRACE CLEAR?
  no  -> information refusal
eligible unit?
  no  -> capacity refusal
  yes -> allocate first
```

### TODO 3

Require an earlier event, same situation, same record chain, later version, and
visible evidence. Append one repair with no selected resource.

## Move-on checks

| Point | Ask |
|---|---|
| Before setup | What does TRACE check? What does the controller check? |
| Before coding | Why do Cases 2 and 3 refuse for different reasons? |
| After TODO 1 | What breaks a travel-time tie? |
| After TODO 2 | Which branch prevents HOLD from reaching resource selection? |
| After TODO 3 | Which earlier event remains in history? |
| After what-if | What changed while TRACE stayed CLEAR? |
| Exit | Why is CLEAR not the same as allocation? |

## Instructor-only boundaries

- Do not expose hidden truth or lineage.
- Do not run validation commands.
- Do not edit frozen scenario or policy files.
- Keep Reference, LEAP, debate, and regret outside this component.
- Do not distribute the solution or instructor branch.
- For a projected completion, use the private reveal procedure in
  [`video/recording_script.md`](video/recording_script.md); it keeps the
  ordinary student filename and commands.
- Do not ask students to share personal paths, accounts, or full screens.
