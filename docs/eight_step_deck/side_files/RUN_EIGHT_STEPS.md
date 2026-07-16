# Run the Eight-Step Flood-SAR Episode

```bash
source "$HOME/miniforge3/etc/profile.d/conda.sh"
conda activate trace-jepa
cd /path/to/trace_jepa_flood_sar_starter
python -m pip install -e ".[dev]"
pytest

trace-jepa-call \
  --call-file examples/calls/riverside_call.txt \
  --output artifacts/runs/call_001
```

Open the outputs on macOS:

```bash
open artifacts/runs/call_001/figures/mission_controller_knowledge.svg
open artifacts/runs/call_001/figures/simulation_ground_truth.svg
open artifacts/runs/call_001/figures/action_timeline.svg
```

Inspect the durable history:

```bash
cat artifacts/runs/call_001/timeline.txt
python -m json.tool artifacts/runs/call_001/summary.json
cat artifacts/runs/call_001/records/trace.jsonl
cat artifacts/runs/call_001/commitments/commitments.jsonl
```
