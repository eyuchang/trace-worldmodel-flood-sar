# TRACE Small SAR — Start Here

Work from the repository root. This required route takes about 2.5–4 hours and
does not use debate, regret, a GPU, a learned model, or live data.

## 1. Set up once

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-delta-python311.lock
.venv/bin/python -m pip install -e . --no-deps
.venv/bin/python labs/07_small_sar_codelab/scripts/preflight.py
```

If your instructor approved Python 3.12, change only the first command.

## 2. Run and replay Small

```bash
sar_work_root="$(mktemp -d)"
.venv/bin/trace-jepa-delta-small run --output "$sar_work_root/run"
.venv/bin/trace-jepa-delta-small replay \
  --reference "$sar_work_root/run" \
  --output "$sar_work_root/replay"
```

## 3. Complete exactly three TODOs

Edit:

```text
labs/07_small_sar_codelab/starter/rescue_controller.py
```

Then run:

```bash
TRACE_SMALL_SAR_CONTROLLER=starter .venv/bin/python -m pytest -q \
  labs/07_small_sar_codelab/tests
```

## 4. Run your controller

```bash
.venv/bin/python labs/07_small_sar_codelab/lab_runtime.py \
  --controller starter \
  --case all
```

You should see one allocation, two different refusal reasons, and an
append-only repair. TRACE `CLEAR` is not itself an allocation: compatible
visible capacity must also exist.

Read the full [student README](README.md) for the three tasks, expected output,
teaching comparisons, book replay, interpretation, and troubleshooting.
