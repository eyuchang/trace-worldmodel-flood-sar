# Migrate the Eight-Step v5 Repository to D0.1

The full D0.1 ZIP is the safest option. To apply only the patch to an existing v5 checkout:

```bash
cd "$HOME/Projects/trace_jepa_flood_sar_starter"
cp -R . "../trace_jepa_flood_sar_starter.before-d0.1"
unzip "$HOME/Downloads/trace_jepa_dynamic_workbench_D0_1_patch.zip" -d .
python -m pip install -e ".[ui,dev]"
pytest
trace-jepa-ui --host 127.0.0.1 --port 8000
open http://127.0.0.1:8000
```

The patch is additive except for `pyproject.toml` and `Makefile`, which are replaced with the D0.1 versions. Existing static-emergency-call commands remain available.
