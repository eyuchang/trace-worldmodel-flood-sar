# WF-DFLD-01-REFERENCE calibration feasibility record v1

## Status and scope

This is a development engineering record, not validation evidence. It records
the mandatory resource check performed before the 100-seed truth and
observation fits. No selection, validation, holdout, or confirmatory seed was
derived, loaded, or run.

## Initial adverse result

On the spent descriptive seed `20260812`, before hot-path optimization:

| Stage | Wall time |
|---|---:|
| Physical generation | 1.44 s |
| Exposure generation | 0.57 s |
| Truth generation | 15.51 s |
| Observation generation | 0.01 s |

The world contained 13,362 eligible candidate episodes, 40 evaluation
incidents, and 70 evaluation reports. A straight 100-seed projection for truth
generation alone was approximately 25.9 minutes, exceeding the predeclared
15-minute stop boundary. The development fit was therefore not started.

The same feasibility pass also showed that the provisional 7% levee-inspection
share in protocol amendment v2 could not be supported by a single modeled levee
segment under continuous-episode suppression. Protocol amendment v3 preserves
that adverse result and corrects the synthetic target before any fitting.

## Behavior-preserving engineering correction

The generation hot path now:

- computes structure/tick hazard, access, occupancy, vulnerability, and subject
  signatures once and reuses them across incident types;
- caches repeated subject signatures;
- avoids constructing Pydantic candidate objects for every rejected tick while
  retaining the exact canonical attempt-chain digest; and
- caches the immutable keyed-randomness prefix.

For seed `20260812`, the optimized path reproduced these pre-change digests
exactly:

- truth: `bc4df744746d424ca0d7cfb339ea53565ab78c06ec30845a14a3c321bdb634d6`
- public reports: `571fd585cea7e549e1c169c725784564b4410f24e3f7321c3399ebbbe164bbcf`

The complete scenario-generation wall time fell from 18.35 seconds to 10.03
seconds on the same local host. This is a descriptive local measurement; the
canonical environment must be measured separately before a scientific freeze.

## Constructed design-scale proxy

After adding an exact temporal index to the visible-evidence graph, a
non-scientific proxy processed 2,900 constructed reports through four logical
authority graphs. Reports spanned the full 96-hour interval and used only
controller-visible fields.

| Quantity | Result |
|---|---:|
| Graph observations | 11,600 |
| Graph elapsed time | 7.102 s |
| Traced Python peak | 27,247,657 bytes |
| Conservative projected bundle | 351,404,032 bytes |
| Conservative projected peak memory | 819,708,969 bytes |

The projection uses a 32 MiB invariant-bundle allowance, 16 KiB per incident,
24 KiB per report-authority runtime contribution, a 512 MiB invariant-process
allowance, 32 KiB per incident in memory, and 64 KiB per report in memory. These
deliberately conservative arithmetic allowances remain below the 1 GiB disk and
2 GiB memory stop boundaries. The proxy does not establish end-to-end simulator
runtime; the first calibrated single-world run must be measured before any
multi-seed runtime execution.

## Remaining gate

Truth fitting may proceed only through a compact, streaming sufficient-
statistics pass whose measured 100-seed projection is below 15 minutes. The
observation fit starts only after the global truth coefficients and complete
truth-fit audit are frozen.
