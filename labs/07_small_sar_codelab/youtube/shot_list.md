# Screen-Capture Shot List

Use a clean local checkout with a generic shell prompt such as `(trace-lab) $`.
Do not show Finder, browser accounts, Git remotes, home-directory paths,
notifications, tokens, email, or private repository information.

| Time | Student question | Visual | Release check |
|---:|---|---|---|
| 00:00 | What am I building? | Minimal welfare-check mission card | One question and one promise; no jargon |
| 00:35 | How does a call become an action? | Reveal call → evidence → TRACE → controller → saved action | Define SAR and evidence aloud |
| 01:40 | What does TRACE do? | TRACE question beside controller question | `CLEAR` visibly means “continue,” not “dispatch” |
| 02:50 | What can my controller return? | Allocate, two refusal reasons, repair | State that repair means a record update |
| 03:55 | Is my computer ready? | Run preflight | Five plain-language PASS lines |
| 04:50 | What does the simulator produce? | Fresh run and replay terminal | Explain counts and `byte-identical` |
| 06:00 | What do the decisions look like? | Reveal four friendly cases one by one | Welfare, levee, medical, later update all explained |
| 07:35 | Which units can help? | Two-resource example beside TODO 1 | Define capability and deterministic ordering |
| 08:50 | Should a unit be sent? | Three-row decision table beside TODO 2 | Information and capacity refusals are distinct |
| 10:20 | What if information changes later? | Version 2 and version 4 timeline beside TODO 3 | Earlier allocation remains visible |
| 11:35 | How do I know my code works? | Green tests, then student walkthrough | Failure names remain readable |
| 12:50 | What changes when capacity changes? | Two what-if results | TRACE remains `CLEAR` in both |
| 13:55 | What did I learn? | Four-item student checklist | End with one short simulation note |

## Terminal and editor appearance

- 1920×1080 canvas, 16:9.
- Terminal font 20–24 pt; editor font 20 pt.
- Maximum 88 terminal columns.
- Dark background with at least WCAG AA text contrast.
- Disable command-history suggestions that can reveal personal paths.
- Replace the default hostname and prompt with generic text.
- Keep the cursor still while narration explains output.
- Show only one TODO at a time; do not reveal the solution file.

## Reset sequence before every take

```bash
git diff -- labs/07_small_sar_codelab/starter/rescue_controller.py
.venv/bin/python labs/07_small_sar_codelab/scripts/preflight.py
sar_work_root="$(mktemp -d)"
```

Use a separately prepared solved starter for the later shots. Do not record or
distribute the instructor solution.
