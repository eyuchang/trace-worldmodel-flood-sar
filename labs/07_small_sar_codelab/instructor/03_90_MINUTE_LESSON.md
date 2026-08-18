# Ninety-Minute Lesson Run of Show

This is a complete short alternative to the full workshop. Use it only when
the prepared environment is already working. Students implement TODO 2; the
instructor demonstrates how TODOs 1 and 3 complete the larger path.

Total teaching time: **90 minutes**.

## Required preparation

- Every machine must already pass `python workshop.py check`.
- Students must have the same full student workspace and README.
- Open the instructor solution separately for demonstrations; never distribute
  it in the student ZIP.
- Keep [`04_LIVE_QUICK_REFERENCE.md`](04_LIVE_QUICK_REFERENCE.md) available.

## Learning outcome

At the end, students should be able to implement and explain:

```text
TRACE not CLEAR                 -> information refusal
TRACE CLEAR + no eligible unit -> capacity refusal
TRACE CLEAR + eligible unit    -> allocation
```

They should also be able to explain, from demonstrations, where resource
eligibility and later repair fit in the full system.

## Schedule

| Time | Activity | Slides |
|---:|---|---:|
| 0:00–0:12 | Mission, visible evidence, TRACE versus controller | 1–4 |
| 0:12–0:20 | Setup confirmation and scenario summary | 5–6 |
| 0:20–0:35 | Four-case walkthrough | 7 |
| 0:35–0:45 | Demonstrate TODO 1 and give students its result | 8 |
| 0:45–1:10 | Students implement and test TODO 2 | 9 |
| 1:10–1:20 | Demonstrate TODO 3 | 10 |
| 1:20–1:27 | Demonstrate capacity changes and replay | 11–12 |
| 1:27–1:30 | Exit explanation | 13 |

## 0:00–0:12 — Establish the two questions

Show Slides 1–4 and the student README system diagram.

Say:

> TRACE checks whether visible information is ready to use. The controller then
> checks whether a suitable unit is actually available. Today you will code
> the point where those two answers become an allocation or refusal.

Ask:

1. “Can the controller read the simulation's hidden answer key?”
2. “Does CLEAR mean a unit has already been selected?”

Move on only after the room answers “no” to both.

## 0:12–0:20 — Confirm setup and connect to Small

Students run:

```bash
python workshop.py check
python workshop.py scenario
```

Do not troubleshoot installations live. Move anyone without `READY` to a
prepared machine.

Read the scenario summary as controller events: 8 allocated, 12 refused, and 8
repaired. Point once to the six-file call-to-outcome path.

## 0:20–0:35 — Teach the four cases

Students run:

```bash
python workshop.py walkthrough
```

Ask the room to classify each case:

| Case | Information ready? | Eligible unit? | Result |
|---|---:|---:|---|
| Welfare check | yes | yes | allocate |
| Levee inspection | no | not checked | information refusal |
| Medical response | yes | no | capacity refusal |
| Later welfare report | later update | no new check | append repair |

Move on when students can explain why the two refusals differ.

## 0:35–0:45 — Demonstrate TODO 1

Show the four eligibility rules and the deterministic sort. Do not ask students
to type TODO 1 during the short lesson.

On the projected instructor copy, show a completed `eligible_resources`
function and run:

```bash
python workshop.py test 1
```

Students should understand its output as an ordered tuple of usable units.
Their own TODO 1 may remain unfinished in this route.

## 0:45–1:10 — Students implement TODO 2

Students open `exercise/rescue_controller.py` and work only inside
`decide_rescue`.

Keep this table visible:

| TRACE | Eligible unit? | Return |
|---|---:|---|
| not CLEAR | either | information refusal |
| CLEAR | no | capacity refusal |
| CLEAR | yes | allocation |

Because TODO 2 calls TODO 1, students may temporarily use this instructor-
provided line at the point where eligible units are needed:

```python
eligible = tuple(
    sorted(
        (
            unit
            for unit in resources
            if unit.currently_available
            and unit.route_reachable
            and unit.route_id == request.route_id
            and request.required_capability in unit.capabilities
        ),
        key=lambda unit: (unit.routed_travel_s, unit.resource_id),
    )
)
```

This line is a short-route teaching aid. In the full route, students call their
own `eligible_resources` function instead.

Students run:

```bash
python workshop.py test 2
```

Move on when the five TODO 2 tests pass and students can identify both refusal
branches.

## 1:10–1:20 — Demonstrate TODO 3

Show the timeline:

```text
version 2 allocation -> later visible information -> append version 4 repair
```

On the instructor copy, point to the five validations and the final return:

```python
return (*history, repair)
```

Ask why replacing the tuple would erase useful history. Demonstrate the two
repair tests; students do not type TODO 3 in this route.

## 1:20–1:27 — Demonstrate comparison and replay

Use an instructor copy with all TODOs complete:

```bash
python workshop.py what-if
python workshop.py replay
```

Ask what stayed fixed during the capacity comparison. Answer: TRACE remained
`CLEAR`; only the resource snapshot changed.

## 1:27–1:30 — Exit explanation

Each pair completes:

> TRACE checks __________. The controller checks __________. A request may be
> refused after CLEAR when __________.

The short lesson is complete when students can answer all three blanks, even
though they did not personally implement TODOs 1 and 3.

## If the full lesson must switch to this route

1. Finish the current segment rather than interrupting students mid-function.
2. Announce that TODO 2 is now the required coding outcome.
3. Use the table above and the short-route eligibility snippet.
4. Demonstrate, rather than assign, TODO 3.
5. Preserve the final capacity comparison and exit explanation.

Do not simply tell students to “skip ahead” in the full README without this
transition; that leaves unfinished dependencies unexplained.
