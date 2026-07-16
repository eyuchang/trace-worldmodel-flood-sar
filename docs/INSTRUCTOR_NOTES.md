# Instructor Notes

## Teach the cast before the stack

Do not begin with V-JEPA, latent spaces, or policy thresholds. Begin with `MISSION_BRIEF.md` and the three SVG views.

Ask every student to answer:

1. Who owns hidden ground truth?
2. What does the Mission Controller know initially?
3. What does the drone observe, and why does it not own hidden truth or score the run?
4. Who proposes actions?
5. Who predicts consequences?
6. Who calls TRACE?
7. Who supplies legal or organizational authority?
8. Who evaluates the run after it ends?

Students who cannot answer these questions should not proceed to the code.

## Recommended course order

1. operational cast and scenario visualization;
2. durable contracts and append-only history;
3. mock closed loop;
4. V-JEPA feature cache;
5. action-conditioned predictor;
6. semantic probes and calibration;
7. revision and localized repair.

## Hardcoded fixtures

The first predictor outputs are deterministic fixtures. State explicitly that this is standard unit-test practice and not an empirical result. The fixture exists to test the accountability response to a known combination:

```text
high predicted success + low support + high OOD -> HOLD
```

Later labs replace the fixture with learned components while keeping the same record and gate interfaces.

## Authority fixture

`IncidentCommander` is a deterministic stand-in for an external approval interface. It shows that technical admissibility and human authority are separate. Do not present it as a simulation of actual incident command.

## macOS

Core mode is supported on an ordinary Apple Silicon Mac with native `osx-arm64` Conda and Python 3.12. Students can activate Miniforge explicitly without changing shell initialization:

```bash
source "$HOME/miniforge3/etc/profile.d/conda.sh"
conda activate trace-jepa
```

The optional JEPA/video path is easier to support on a Linux GPU machine or validated container.

## Ethical boundary

Use controlled exercises, licensed footage, synthetic scenes, or non-identifiable public data. Do not use identifiable victims or operational emergency data without appropriate approval. The teaching system has no autonomous dispatch authority.
