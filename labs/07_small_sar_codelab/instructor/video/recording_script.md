# Record This Video: Flood Rescue Controller Code-Along

Use this as the **only filming guide** for the student video. It combines the
former shot list, narration, screen directions, private reveal procedure, exact
commands, and reset procedure in one place.

The final video is a real, narrated screen recording of the student README,
terminal, and editor. Do **not** use slides, the silent review draft, a
solution file, the research repository, or a browser tab as footage.

**Target:** 12–15 minutes.

**Format:** screen plus narration; no camera.

**Audience:** students with no prior SAR or TRACE experience.

**File they see you edit:** `exercise/rescue_controller.py`.
**Commands they see you run:** `python workshop.py ...`.

## 1. Set up the recording workspace before opening Screen Recording

Use a disposable instructor-only copy. It starts with the same three TODOs the
students receive, but it lets you privately reveal one completed function at a
time between takes.

In Terminal, run these commands once. Replace the two quoted paths with the
locations on your computer, then keep the variable names unchanged for every
later private reveal and reset command:

```bash
CODELAB_DIR="/path/to/trace-jepa-small-sar-codelab"
DEMO_DIR="/path/to/trace-small-sar-video-demo"

cd "$CODELAB_DIR"

python3 labs/07_small_sar_codelab/instructor/tools/demo_workspace.py prepare \
  --workspace "$DEMO_DIR"

cd "$DEMO_DIR"
python3 setup_workshop.py
source .venv/bin/activate
python workshop.py check
```

The final command must show five `PASS` lines and `READY`.

Leave this first terminal open but outside the recording area. It is your
**private terminal**: it retains `CODELAB_DIR` and `DEMO_DIR`, and you will use
it only during the three off-camera reveals and a reset. If you close it, enter
the two variable-assignment lines again before using a reveal command.

Open a second terminal for the recording. In that visible terminal, run:

```bash
cd "$DEMO_DIR"
source .venv/bin/activate
PS1='workshop % '
clear
```

The generic prompt and blank history prevent a personal username or path from
appearing on screen. Keep this visible terminal in the `$DEMO_DIR` folder for
every student-facing command below.

Open this folder in your editor:

```text
the folder stored in `$DEMO_DIR`
```

Open these three items before recording:

1. `README.md`;
2. `exercise/rescue_controller.py`; and
3. a terminal in the same folder with `.venv` activated.

Do not open `instructor/solution/rescue_controller.py` on the recorded
screen. The private reveal tool uses it off screen.

## 2. Make the recording screen clean and readable

1. Turn on Do Not Disturb and close Mail, Messages, browser tabs, Finder
   windows, and anything showing personal information.
2. In the editor and terminal, set text to at least 20 pt. Use 24 pt if it
   still fits comfortably.
3. When showing code, place the editor on the left or top and the terminal on
   the right or bottom. Show only one TODO at a time.
4. On a Mac, press `Command-Shift-5`, choose **Record Selected Portion**,
   select only the editor and terminal area, and select your microphone.
5. Record each numbered section below as a separate take. This lets you redo a
   small mistake without restarting the whole video. Click the square **Stop**
   button in the menu bar after every take; trim and join the takes in the
   listed order only after you finish all twelve.

There is no title slide. Start immediately on the README. Use short, natural
pauses after each terminal command so students can read the output.

## 3. The exact recording sequence

### Take 1 — What students will build (0:00–0:35)

**Put on screen:** `README.md`, at “What system are you building?” Show the
diagram and its text alternative. Do not show the whole README.

**Do:** point to the route from the flood call to TRACE to the controller.

**Say:**

> A welfare-check call arrives during a simulated flood. We have information
> about the call, but we also have limited response units. In this lesson, you
> will write the controller that decides whether to allocate a suitable unit,
> refuse with a reason, or later append a correction. SAR means search and
> rescue: helping people during an emergency.
>
> TRACE is the decision notebook. It checks whether the visible information is
> ready to use. Your controller checks whether a suitable response unit is
> actually available.

**Leave on screen:** the two questions—TRACE checks information readiness; the
controller checks resource availability.

### Take 2 — Find the only file to edit (0:35–1:10)

**Put on screen:** the README’s “Start here,” workspace map, and “Workshop
Breakdown.” Scroll only far enough to show those sections.

**Do:** point first to `exercise/rescue_controller.py`, then to
`python workshop.py ...`.

**Say:**

> This README is your route map. You will edit exactly one file,
> `exercise/rescue_controller.py`, and run every workshop action with
> `python workshop.py`. First we will run the supplied scenario. Then you
> will complete three focused functions, test each one, and run the resulting
> controller.
>
> Before Step 1, the README gives complete Windows, macOS, and Linux setup
> instructions. I will show the macOS and Linux commands here; Windows students
> use the PowerShell block in the README.

### Take 3 — Set up this laptop and check it (1:10–1:45)

**Put on screen:** the macOS/Linux setup block in the README. Then switch to
the terminal. The terminal should be inside `trace-small-sar-video-demo`.

**Type and show exactly:**

```bash
python3 setup_workshop.py
source .venv/bin/activate
python workshop.py check
```

If setup already says the environment is ready, that is fine. Keep the final
`check` output on screen long enough to read its five labels.

**Say:**

> The ZIP contains everything this workshop needs. The setup command creates a
> private Python environment in this folder. It does not install packages,
> download a model, or require a GPU. After activation, everyone uses the same
> `python workshop.py` commands.
>
> Five PASS lines and READY mean you can continue. The checks cover Python, the
> workshop files, the four teaching cases, the test runner, and the practice
> output folder.

Do not show a package manager, a `pip install` command, or unrelated terminal
history.

### Take 4 — Run the completed small scenario (1:45–2:40)

**Put on screen:** terminal only.

**Type and show exactly:**

```bash
python workshop.py scenario
python workshop.py walkthrough
```

After `scenario`, pause on:

```text
Scenario complete: 1 allocated, 2 refused, 1 repaired.
```

After `walkthrough`, leave all four printed cases visible.

**Say:**

> The scenario command runs a supplied completed flood session. It does not
> call the three unfinished functions we are about to write. The saved path is
> call, evidence, TRACE record, controller decision, commitment, and outcome.
>
> This small scenario records one allocation, two refusals, and one repair.
> The walkthrough now zooms in on four completed decisions.

### Take 5 — Read the four decisions (2:40–3:35)

**Put on screen:** the walkthrough output. Keep the terminal large enough to
read. Do not replace this with a slide.

**Do:** trace each printed case with the cursor as you discuss it.

**Say:**

> First, TRACE says CLEAR and a suitable engine is available, so the controller
> allocates it. Second, the levee-inspection information is on HOLD, so the
> controller refuses before checking resources. A levee is a barrier that helps
> hold back floodwater.
>
> Third, a medical response is CLEAR, but suitable units are busy, so the
> controller refuses because of capacity. Finally, later visible evidence
> appends a repair: it keeps the version-two allocation and adds version four.
> It does not reserve another unit.
>
> CLEAR allows the resource check. It does not mean a unit was sent.

### Take 6 — TODO 1: choose eligible units (3:35–5:10)

**Put on screen:** `exercise/rescue_controller.py` at
`eligible_resources`. It must still show the original TODO 1 comments and
`NotImplementedError`.

**Do before the pause:** read the four eligibility rules from the comments:
available, reachable, correct route, required capability. Point to the sort
key in the README if needed.

**Say before the pause:**

> A resource is a response unit. Keep it only when it is available, can reach
> the route, matches the requested route, and has the required capability. Then
> sort usable units by travel time and resource ID so the result is repeatable.
>
> Pause the video here and attempt TODO 1. When you are ready, continue to
> compare your implementation with this one.

**Stop recording now. Do not show the next command.**

In the private terminal you left open, reveal TODO 1:

```bash
cd "$CODELAB_DIR"

python3 labs/07_small_sar_codelab/instructor/tools/demo_workspace.py reveal \
  --workspace "$DEMO_DIR" \
  --todo 1
```

Return to the **same** editor tab and file:

```text
exercise/rescue_controller.py
```

Reload the file if the editor has not refreshed it. Resume recording only when
the completed `eligible_resources` function is visible.

**Say after resuming:**

> This version keeps only resources that pass all four checks. The parentheses
> collect those resources, and `sorted` makes their order deterministic:
> first by travel time, then by resource ID. The outer `tuple` returns the
> ordered result. An empty tuple is normal when no unit qualifies.

**Switch to terminal and type:**

```bash
python workshop.py test 1
```

Hold on the passing test before ending the take.

### Take 7 — TODO 2: allocate or refuse (5:10–7:35)

**Put on screen:** `decide_rescue` in the same editor file. It must still
show TODO 2. Briefly show the three-row decision table in the README, then
return to the editor.

**Say before the pause:**

> First make sure the request and TRACE authorization describe the same call
> and situation. A mismatch is invalid input, so raise `ValueError`.
>
> After that, TRACE comes before capacity. HOLD produces an information
> refusal. CLEAR allows us to check units. No eligible unit produces a capacity
> refusal; otherwise allocate the first eligible unit.
>
> Pause here and attempt TODO 2.

**Stop recording. In the private terminal, reveal TODO 2:**

```bash
cd "$CODELAB_DIR"

python3 labs/07_small_sar_codelab/instructor/tools/demo_workspace.py reveal \
  --workspace "$DEMO_DIR" \
  --todo 2
```

Return to the same `exercise/rescue_controller.py` tab and resume recording.

**Say after resuming:**

> The first two checks reject records that describe different situations. Then
> the TRACE branch stops a HOLD before resources are considered. Only a CLEAR
> decision reaches the capacity check. If the eligible-resource tuple is empty,
> the controller refuses; otherwise it allocates the first ordered unit.
>
> HOLD and no capacity are normal refusal outcomes. They are not errors.

**Switch to terminal and type:**

```bash
python workshop.py test 2
```

Hold on the five passing tests before ending the take.

### Take 8 — TODO 3: append a repair (7:35–9:00)

**Put on screen:** `apply_visible_repair` in the same editor file. It must
still show TODO 3.

**Say before the pause:**

> A repair is a correction to the decision record, not physical repair work.
> It can extend history only when there is a prior decision, the belief cluster
> and TRACE record chain match, the version is later, and visible evidence
> supports the update. Each failed consistency check raises `ValueError`.
>
> Pause here and attempt TODO 3.

**Stop recording. In the private terminal, reveal TODO 3:**

```bash
cd "$CODELAB_DIR"

python3 labs/07_small_sar_codelab/instructor/tools/demo_workspace.py reveal \
  --workspace "$DEMO_DIR" \
  --todo 3
```

Return to the same editor file and resume recording.

**Say after resuming:**

> The function checks the earlier history, the situation, the TRACE record
> chain, the later version, and the visible evidence. It then creates one
> repair and returns a new tuple containing the old history followed by that
> repair. The original allocation stays first.

**Switch to terminal and type:**

```bash
python workshop.py test 3
```

Hold on the six passing tests before ending the take.

### Take 9 — Run the completed controller (9:00–10:20)

**Put on screen:** terminal only.

**Type and show exactly:**

```bash
python workshop.py test all
python workshop.py run
```

**Say:**

> All twelve tests are now passing. This run applies your three functions to
> the four teaching cases. The terminal now prints decisions returned by your
> code, not the earlier supplied walkthrough. Compare the results: one
> allocation, two different refusals, and one appended repair.

### Take 10 — Change capacity without changing TRACE (10:20–11:15)

**Put on screen:** terminal only.

**Type and show exactly:**

```bash
python workshop.py what-if
```

**Say:**

> These two runs change only copied resource snapshots. When welfare-check
> units become busy, the controller refuses. When a medical unit becomes
> available, the controller allocates it. TRACE stays CLEAR in both examples.
> That is why CLEAR is not the same as allocation.

### Take 11 — Replay the saved history (11:15–12:10)

**Put on screen:** terminal only.

**Type and show exactly:**

```bash
python workshop.py replay
```

**Say:**

> Replay regenerates the saved teaching history. Byte-identical means every
> saved file matches exactly. It lets us inspect the same decision path again
> rather than treating a rerun as a new result.

Hold on `Replay: byte-identical.` for a moment before ending the take.

### Take 12 — Close the lesson (12:10–13:25)

**Put on screen:** README completion checklist. Return to the terminal replay
result for the final sentence.

**Say:**

> You built the bridge from information to action. A call produced visible
> evidence. TRACE decided whether that evidence could reach the resource check.
> Your controller allocated a suitable unit or refused with a reason. Later
> evidence appended a repair without erasing the earlier decision.
>
> Use the README checklist to finish, reset your practice files if needed, and
> keep experimenting only inside the exercise and tests folders.

## 4. Reset the demo before a new rehearsal or full retake

Stop screen recording first. Then run:

```bash
cd "$CODELAB_DIR"

python3 labs/07_small_sar_codelab/instructor/tools/demo_workspace.py reset \
  --workspace "$DEMO_DIR"

cd "$DEMO_DIR"
source .venv/bin/activate
python workshop.py reset
```

The first command restores the three original TODOs in the same student file.
The second removes only generated `.workshop` output. It does not remove the
demo copy or its local `.venv`.

## 5. Finish and check the recording

1. Place the twelve takes in the exact order above. Trim only mistakes, long
   waits, and the three private reveal transitions. Do not cut away a command
   or its readable output.
2. Keep the three “pause and attempt TODO N” moments. A brief text overlay is
   enough; do not replace the real screen recording with a slide.
3. Add captions from the narration. The chapter order and caption rules are
   in [chapters_and_captions.md](chapters_and_captions.md); its `.srt` file is
   only a timing draft, so align captions to the final spoken recording.
4. Watch the finished video once with sound and once muted. It is ready to
   share for review only if every item below is true:

   - the README, editor, terminal, and their text are readable at 720p;
   - all twelve student commands and their expected outputs are visible;
   - each TODO pause shows the unfinished function before the pause and the
     completed version of the same filename afterward;
   - no reveal command, solution file, research terminal command, browser,
     personal path, notification, account, or camera appears;
   - narration defines SAR, TRACE, CLEAR, HOLD, allocation, refusal, and
     repair before relying on each term; and
   - the final completion checklist remains visible before the close.

5. Do not upload or publish the video until you have approval. The separate
   `recording_checklist.md` is retained only as an administrative handoff
   checklist; you do not need it to film this lesson.

## Optional research-context postscript

Do not include this in the core student video. If Dr. Chang later asks for it,
record a separate 30–45 second postscript and label it:

```text
Separate research-workbench context — not required for this student exercise
```

State that it uses a different dynamic scenario and does not run the student's
three functions. Do not use it to make learned-model or operational-response
claims.
