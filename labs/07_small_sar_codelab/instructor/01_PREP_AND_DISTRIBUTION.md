# Instructor Preparation and Distribution

Use this document before class. During class, use either
[`02_FULL_LESSON_RUN_OF_SHOW.md`](02_FULL_LESSON_RUN_OF_SHOW.md) or
[`03_90_MINUTE_LESSON.md`](03_90_MINUTE_LESSON.md), plus the
[`04_LIVE_QUICK_REFERENCE.md`](04_LIVE_QUICK_REFERENCE.md). For a projected
or recorded code-along, use the single
[`video/recording_script.md`](video/recording_script.md). It includes the
private same-file reveal procedure as well as the recording directions.

The audience is more than 100 college students who know basic Python but have
no prior SAR or TRACE experience. Dr. Chang already knows the system; this
preparation is about a smooth beginner experience, not relearning TRACE.

## Instructor answer key

The complete, tested sample implementation is
[`solution/rescue_controller.py`](solution/rescue_controller.py). Its three
functions match the student exercise exactly:

1. `eligible_resources`;
2. `decide_rescue`; and
3. `apply_visible_repair`.

Keep it private. It is not in the student ZIP. For an actual demonstration,
use the private reveal procedure in the recording script rather than opening
this file before students attempt the relevant TODO.

## 1. Choose the lesson before distributing anything

| Route | Student coding | Total teaching time | Instructor document |
|---|---|---:|---|
| Full workshop | TODOs 1, 2, and 3 | 3 hours 15 minutes, plus local setup if needed | `02_FULL_LESSON_RUN_OF_SHOW.md` |
| Short lesson | TODO 2; TODOs 1 and 3 demonstrated | 90 minutes, plus local setup if needed | `03_90_MINUTE_LESSON.md` |

Do not switch routes halfway through unless a room-wide technical delay makes
the full route impossible.

## 2. Know the BYOD package

Students receive one extracted folder:

```text
trace-small-sar-workshop/
├── README.md
├── setup_workshop.py
├── workshop.py
├── exercise/rescue_controller.py
├── tests/test_rescue_controller.py
└── _support/
```

The ZIP is a standalone student workspace: it contains a small, public-only
teaching runtime and the four teaching cases. It does **not** require the TRACE
repository, a model, GPU access,
network access, package installation, or instructor-provided virtual
environment. The only prerequisite is Python 3.11 through 3.14.

The ZIP excludes:

- the instructor solution and reveal tool;
- the research repository and source code;
- all hidden truth and lineage;
- Reference, LEAP, protected validation, and publication materials; and
- video-production materials.

Do not distribute the full instructor branch or a folder copied from it. Build
and distribute only the standalone student ZIP.

The student `scenario` command writes exactly six controller-visible files. It
does not produce `ground_truth.json` or any other hidden-answer file.

## 3. Support setup on personal laptops

### Preferred preflight

If time permits, send the ZIP and ask students to complete “Before Step 1” in
the README one to seven days before class. They should arrive after seeing the
five `PASS` lines and `READY`.

### Same-day setup

Preflight is helpful, not required. Reserve 10–15 minutes at the start for
students who could not prepare. Project the same commands in the README:

```text
macOS/Linux:  python3 setup_workshop.py
               source .venv/bin/activate
               python workshop.py check

Windows:       py setup_workshop.py
               .\.venv\Scripts\Activate.ps1
               python workshop.py check
```

The setup script only creates a local `.venv`; it installs no packages and
uses no network. Students should never run `pip install` for this workshop.

### Triage order

1. `python3` or `py` missing: send the student to the official Python download
   page named in the README; they need Python 3.11–3.14.
2. `.venv` exists but setup stops: use `--repair` only when the student agrees
   to replace that workspace-local environment.
3. PowerShell blocks activation: switch to Command Prompt and use
   `.venv\Scripts\activate.bat`.
4. A student has neither Python nor permission to install it: pair them with a
   nearby prepared student while a helper resolves the installation. Do not
   turn the lesson into a package-manager session.

Assign one setup helper for every 25–35 students. Setup helpers need only the
first visible error line, never a full desktop, account, or personal path.

## 4. Build the student workspace

From this codelab branch, regenerate the frozen public fixture first:

```bash
python labs/07_small_sar_codelab/tools/build_teaching_fixture.py --overwrite
```

Then build the ZIP into a new output directory:

```bash
python labs/07_small_sar_codelab/tools/make_student_bundle.py \
  --output /path/to/new/trace-small-sar-workshop.zip
```

The builder refuses to overwrite an existing archive. Inspect the archive:
there should be one `trace-small-sar-workshop` directory with `README.md` at
its root, but no `instructor`, `solution`, research source, or hidden-truth
filename.

## 5. Release rehearsal

From the codelab worktree, run:

```bash
python -m pytest -q labs/07_small_sar_codelab/release_tests
```

Then perform a clean BYOD rehearsal:

1. extract the new ZIP into a clean directory;
2. run the appropriate student setup and activation commands;
3. run `python workshop.py check`;
4. in a disposable copy only, apply the three private solution functions or
   use the reveal tool; and
5. run this sequence:

```text
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

- setup reports five `PASS` lines and `READY`;
- the scenario reports 1 allocation, 2 refusals, and 1 repair;
- all twelve behavior tests pass with the reference solution;
- controller output matches the walkthrough;
- replay is byte-identical; and
- no generated file is named `ground_truth.json` or `call_lineage.json`.

## 6. Run a novice navigation rehearsal

Have someone who did not author the lab use the unmodified ZIP on a personal
laptop. Observe without directing them for the first five minutes. Record:

- time to identify the setup commands and the only editable file;
- time to reach `READY`;
- every setup message that causes a question;
- whether they understand the two questions TRACE and the controller answer;
- whether they distinguish information refusal from capacity refusal; and
- whether they understand that repair preserves version 2.

Do not release the package if the person must ask where to go next or needs an
unlisted package installation.

## 7. Prepare the room and materials

- Put the ZIP where every student can download it before the first coding task.
- Project the README, a clean terminal, and the student editor—not slides.
- Set terminal and editor text to at least 20 pt.
- Keep the short troubleshooting table open for helpers.
- Use the private reveal procedure in `video/recording_script.md` for the
  instructor screen; students use their own untouched copy.
- Keep a backup distribution method ready if classroom Wi-Fi is unreliable.

## 8. Scope and safety check

These are instructor responsibilities, not opening-lecture material:

- use only the public teaching fixture and supplied command runner;
- do not expose hidden truth or lineage;
- do not run research, validation, or publication commands;
- do not edit frozen policy, calibration, manifests, or reference runs;
- keep Reference, LEAP, debate, and regret outside this lesson; and
- do not record accounts, notifications, tokens, email, or personal paths.

The student explanation needs only one boundary: this is a simulated
flood-response exercise, and the controller decides from visible evidence.

## Day-before release checklist

- [ ] Lesson route selected.
- [ ] Public fixture regenerated and source hash checked.
- [ ] Student ZIP rebuilt and contents inspected.
- [ ] Release tests passed.
- [ ] Clean macOS/Linux setup rehearsal passed.
- [ ] Clean Windows setup rehearsal passed, if Windows is supported in class.
- [ ] Novice BYOD rehearsal passed.
- [ ] README, terminal, and editor checked for readability.
- [ ] Setup helpers assigned and given `04_LIVE_QUICK_REFERENCE.md`.
- [ ] Instructor reveal copy prepared without projecting the solution.
- [ ] No instructor, solution, research-source, or hidden-answer file appears in the student ZIP.
