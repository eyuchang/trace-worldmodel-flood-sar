# Screen-Capture Shot List

Use a clean local checkout with a generic shell prompt such as `(trace-lab) $`.
Do not show Finder, a browser account, Git remotes, a home-directory path,
notifications, tokens, email, or private repository information.

| Time | Visual | Capture instruction | Release check |
|---:|---|---|---|
| 00:00 | Title card | Full-screen 16:9 card; no desktop chrome | “No GPU” and “Offline execution” visible |
| 00:40 | Objectives/scope | Two-column card | Synthetic/non-operational visible |
| 01:40 | Architecture | Reveal public call through repair | Hidden truth shown only as an excluded boundary |
| 02:55 | Preflight terminal | Run exact README command | Five PASS lines; no personal path |
| 03:55 | Fresh run/replay | Run in fresh temporary directory | Counts and byte-identical line visible |
| 05:00 | Public book cases | Use `--controller book --case all` | No solution file shown |
| 06:30 | TODO 1 | Crop editor to function and type definitions | No solution tab or minimap preview |
| 07:45 | TODO 2 | Decision table, then starter function | CLEAR and allocation separated |
| 09:15 | TODO 3 | Version-chain diagram and starter function | Old allocation remains visible |
| 10:30 | Tests/student run | Show green summary and four decisions | Instructor-only filenames hidden |
| 11:30 | Variants | Side-by-side terminals | “TEACHING-ONLY” watermark visible |
| 12:45 | Book replay | Show exact reference and bound report | Do not show protected study commands |
| 13:45 | Close | Checklist, then limitations card | Limitations card remains at least 12 seconds |

## Terminal appearance

- 1920×1080 canvas, 16:9.
- Terminal font 20–24 pt; editor font 20 pt.
- Maximum 88 terminal columns.
- Dark background with at least WCAG AA text contrast.
- Disable command history suggestions that can reveal personal paths.
- Replace the default hostname and prompt with generic text.
- Keep the cursor still while narration explains output.

## Reset sequence before every take

```bash
git diff -- labs/07_small_sar_codelab/starter/rescue_controller.py
.venv/bin/python labs/07_small_sar_codelab/scripts/preflight.py
sar_work_root="$(mktemp -d)"
```

Use a separately prepared solved starter for the later shots. Do not record the
reference solution file or distribute it with the student overlay.
