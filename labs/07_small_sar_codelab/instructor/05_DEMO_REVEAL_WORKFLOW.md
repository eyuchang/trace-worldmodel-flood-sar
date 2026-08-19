# Instructor Demo Reveal Workflow

Use this only for a projected demonstration or recorded code-along. Students
work in their own untouched workspace. The reveal tool is not in the student
ZIP and must not be projected before students have had time to attempt a TODO.

The tool changes the same filename students edit:

```text
exercise/rescue_controller.py
```

That means the commands after each reveal are exactly the normal student
commands: `python workshop.py test 1`, `python workshop.py run`, and so on.
There is no decoy file and no switch to a separate solution workspace.

## Before class or recording

Create one disposable demo copy in a folder outside the student ZIP. The
destination must not already exist.

```bash
python instructor/tools/demo_workspace.py prepare \
  --workspace /path/to/trace-small-sar-instructor-demo
```

Open that new folder in the editor. It starts with the exact three TODOs that
students receive. Run the same BYOD setup once in the demo copy:

```bash
cd /path/to/trace-small-sar-instructor-demo
python3 setup_workshop.py
source .venv/bin/activate
python workshop.py check
```

On Windows, use the Windows setup and activation commands from the student
README instead.

## During the lesson

1. Project the TODO in `exercise/rescue_controller.py`.
2. State the coding task and give students the planned attempt time.
3. Stop projecting while you reveal the reference implementation, or make a
   clean edit in the recording.
4. Reveal only the completed step in the same demo copy:

```bash
python /path/to/labs/07_small_sar_codelab/instructor/tools/demo_workspace.py \
  reveal --workspace . --todo 1
```

5. Return to the editor and run the ordinary student command:

```bash
python workshop.py test 1
```

Repeat with `--todo 2` and `--todo 3`. The tool refuses to reveal steps out of
order, replace an ordinary student workspace, or overwrite a changed TODO.

## Resetting the demo copy

Between rehearsals, restore all three TODOs with:

```bash
python /path/to/labs/07_small_sar_codelab/instructor/tools/demo_workspace.py \
  reset --workspace .
```

Check what has been revealed at any time:

```bash
python /path/to/labs/07_small_sar_codelab/instructor/tools/demo_workspace.py \
  status --workspace .
```

Do not use `reset` in a student’s workspace. The tool requires the marker that
it creates only in its disposable instructor demo copy.
