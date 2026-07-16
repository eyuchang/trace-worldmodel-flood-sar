.PHONY: help install-core install-jepa verify visualize test call-demo demo synthetic-data train-toy clean

help:
	@printf '%s\n' \
	  'make install-core   Install laptop-safe dependencies' \
	  'make install-jepa   Install optional JEPA/video dependencies' \
	  'make verify         Check project directories and imports' \
	  'make visualize      Render the operational cast and two scenario views' \
	  'make test           Run implementation-invariant tests' \
	  'make call-demo      Run from the example emergency call' \
	  'make demo           Run the pre-filled deterministic flood-SAR loop' \
	  'make synthetic-data Generate the teaching trajectory dataset' \
	  'make train-toy      Train the reference action-prefix predictor' \
	  'make clean          Remove local Python/test caches'

install-core:
	python -m pip install -e ".[dev]"

install-jepa:
	python -m pip install -e ".[jepa]"

verify:
	PYTHONPATH=src python -m trace_jepa.verify

visualize:
	PYTHONPATH=src python -m trace_jepa.scenario.visualize --output artifacts/runs/scenario_brief

test:
	PYTHONPATH=src pytest -q

call-demo:
	PYTHONPATH=src python -m trace_jepa.emergency_cli --call-file examples/calls/riverside_call.txt --output artifacts/runs/call_001

demo:
	PYTHONPATH=src python -m trace_jepa.demo --output artifacts/runs/class_demo

synthetic-data:
	python scripts/generate_synthetic_dataset.py --episodes 1000 --output data/processed/synthetic_flood_trajectories.npz

train-toy:
	python scripts/train_action_predictor.py --dataset data/processed/synthetic_flood_trajectories.npz --output models/checkpoints/toy_action_predictor.pt --epochs 100

clean:
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache build dist
	find src -maxdepth 1 -type d -name '*.egg-info' -prune -exec rm -rf {} +

install-ui:
	python -m pip install -e ".[ui,dev]"

ui:
	trace-jepa-ui --host 127.0.0.1 --port 8000

ui-open:
	open http://127.0.0.1:8000
