# Instructor Preparation and Distribution

Use this document before class. During class, use either
[`02_FULL_LESSON_RUN_OF_SHOW.md`](02_FULL_LESSON_RUN_OF_SHOW.md) or
[`03_90_MINUTE_LESSON.md`](03_90_MINUTE_LESSON.md), plus the
[`04_LIVE_QUICK_REFERENCE.md`](04_LIVE_QUICK_REFERENCE.md).

The audience is more than 100 college students who know basic Python but have
no prior search-and-rescue or TRACE experience. Dr. Chang already knows the
system; preparation should focus on delivery, not relearning TRACE.

## Instructor answer key

The complete, tested sample implementation of all three student functions is
[`solution/rescue_controller.py`](solution/rescue_controller.py). Its function
names, signatures, and order match the student exercise exactly:

1. `eligible_resources`;
2. `decide_rescue`; and
3. `apply_visible_repair`.

Keep this file open privately when reviewing student code or demonstrating an
answer. It passes the same eight behavior tests students run. Do not place it
inside the student workspace or display it before the relevant coding period
has ended.

## 1. Choose the lesson before distributing anything

Choose one route:

| Route | Student coding | Total time | Instructor document |
|---|---|---:|---|
| Full workshop | TODOs 1, 2, and 3 | 3 hours 15 minutes | `02_FULL_LESSON_RUN_OF_SHOW.md` |
| Short lesson | TODO 2; TODOs 1 and 3 are demonstrated | 90 minutes | `03_90_MINUTE_LESSON.md` |

Do not switch routes halfway through unless a room-wide technical delay makes
the full route impossible. The short lesson includes an explicit transition
for that situation.

## 2. Know the two-layer setup

Students open only the standalone student workspace:

```text
trace-small-sar-workshop/
├── README.md
├── workshop.py
├── exercise/rescue_controller.py
├── tests/test_rescue_controller.py
└── _support/
```

The prepared Python environment supplies the pinned TRACE Small runtime and
public scenario artifacts. Students do not open or navigate the research
repository.

The student ZIP excludes:

- the instructor solution;
- instructor and video materials;
- release and scientific-boundary tests;
- TRACE research source;
- scenario and geography data; and
- protected validation material.

## 3. Prepare every machine

Use the recorded Small base commit:

```text
3f912bdf3fbacb679063da9ed2ce15a2330b91ab
```

On each managed image:

1. provision Python 3.11, or the tested Python 3.12 contingency;
2. install the hash-locked Delta requirements;
3. install the recorded TRACE checkout in editable mode with `--no-deps`;
4. ensure the workshop terminal starts with that environment active;
5. disable automatic package and environment updates until the session ends;
6. keep the research checkout outside the folder students open; and
7. verify that `python workshop.py check` can locate the editable TRACE
   installation without an environment variable.

Avoid a live dependency on package indexes, Git hosting, container registries,
or model downloads. A simultaneous setup event is the largest avoidable risk
for a room of this size.

## 4. Build the student workspace

From the instructor codelab branch, create a new output directory and run:

```bash
python labs/07_small_sar_codelab/tools/make_student_bundle.py \
  --output /path/to/new/trace-small-sar-workshop.zip
```

The builder refuses to overwrite an existing archive. Extract it and confirm
that it creates one `trace-small-sar-workshop` directory with `README.md` at
that workspace root.

Do not distribute the full instructor branch. Do not ask students to apply an
overlay to a research checkout.

## 5. Run the release checks

From the codelab worktree:

```bash
python -m pytest -q labs/07_small_sar_codelab/release_tests
```

Then perform a clean student rehearsal:

1. extract the new ZIP into a clean directory;
2. open only `trace-small-sar-workshop`;
3. copy the instructor solution over `exercise/rescue_controller.py` in that
   disposable rehearsal copy;
4. run every command in this order:

```text
python workshop.py
python workshop.py check
python workshop.py scenario
python workshop.py walkthrough
python workshop.py test 1
python workshop.py test 2
python workshop.py test 3
python workshop.py test all
python workshop.py run
python workshop.py what-if
python workshop.py replay
python workshop.py reset
```

Required outcomes:

- five setup checks pass;
- the scenario reports 8 allocations, 12 refusals, and 8 repairs;
- all eight behavior tests pass with the solution;
- the four controller decisions match the walkthrough;
- both replays are byte-identical;
- reset removes generated output but keeps the exercise code; and
- no command writes into the research checkout's protected directories.

## 6. Run a novice release rehearsal

Have someone who did not author the lab use the unmodified student package.
This is a release gate in addition to automated testing.

Observe without directing them for the first five minutes. Record:

- time to identify the only editable file;
- time to reach five `PASS` lines;
- whether they understand what `python workshop.py` displays;
- every term they encounter before it is explained;
- every moment they browse `_support/` or look for another guide;
- which TODO instruction they interpret differently from the intended rule;
- whether they can explain information refusal versus capacity refusal; and
- whether they can explain why repair version 4 does not erase version 2.

Do not release the package if the person must ask where to go next.

## 7. Prepare the room

- Assign one helper per 25–35 students and one setup lead.
- Put the ZIP on managed machines before students arrive.
- Open terminals in the extracted student workspace with the environment active.
- Set projected terminal and editor text to at least 20 pt.
- Keep printed or locally hosted copies of the student README and quick reference.
- Prepare three room-status cards or poll choices: **Setup**, **Code**, and
  **Explain**.
- Decide how helpers will receive the first visible error line without asking
  students to share personal directories or full screens.

## 8. Prepare the teaching materials

The full lesson uses the 13-slide sequence in `video/`:

1. mission;
2. call-to-decision path;
3. TRACE versus controller;
4. allocate, refuse, repair;
5. setup;
6. complete scenario;
7. four cases;
8. TODO 1;
9. TODO 2;
10. TODO 3;
11. tests and complete run;
12. capacity changes; and
13. student explanation.

Verify that every terminal line is readable without horizontal scrolling. The
silent review video is for timing and visual review; it is not the final
personal recording.

## 9. Scope and safety check

These are preparation responsibilities, not an opening lecture for students:

- use only the public teaching cases and supplied command runner;
- do not expose hidden truth or hidden lineage;
- do not run development or protected validation roles;
- do not edit Small policy, calibration, manifests, or saved reference runs;
- do not introduce Reference, LEAP, debate, or regret code into this lesson;
- do not describe capacity variants as research experiments; and
- do not record accounts, notifications, tokens, email, or personal paths.

The student explanation needs only one boundary: this is a simulated
flood-response exercise, and the controller decides from visible evidence.

## Day-before release checklist

- [ ] Lesson route selected.
- [ ] Approved commit recorded.
- [ ] Prepared Python environment active on every machine image.
- [ ] Student ZIP rebuilt from the final source.
- [ ] ZIP contents inspected.
- [ ] Release tests passed.
- [ ] Full clean-room command rehearsal passed.
- [ ] Novice navigation rehearsal passed.
- [ ] Projected slides and terminal checked for readability.
- [ ] Helpers assigned and given `04_LIVE_QUICK_REFERENCE.md`.
- [ ] Offline copies available.
- [ ] No instructor, solution, video, or release file appears in the student ZIP.
