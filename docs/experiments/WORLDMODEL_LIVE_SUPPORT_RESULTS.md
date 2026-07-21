# Development-Only Live World-Model Results

## Registered scope

The live qualification used 12 synthetic development episodes and opened no
held-out or RQ1-RQ5 data. Learned outputs were recorded as non-licensing evidence
and were not used by the TRACE gate or planner.

## Upstream verification

The official V-JEPA 2.1 adapter matched the pinned upstream implementation with
maximum absolute error `0.0` for both direct and masked-predictor forward paths.
The minimal DINO-WM port matched the pinned upstream forward output with maximum
absolute error `0.0`; all 25 state-dictionary keys were identical.

These parity results validate the registered adapter computations. They do not
make the Flood-SAR DINO-WM adaptation identical to the upstream robotics runtime.

## Live qualification

Each model completed 36 uncached learned requests: 12 aligned, 12 static-video,
and 12 camera-stratified shuffled-video requests. Each also completed 12
structured and 12 simple-visual reference requests. Independent verification
reloaded 60 artifacts and reproduced 60 cache hits per model.

| Backend | Aligned vs. static differed | Aligned vs. shuffled differed | Median uncached latency | p95 latency |
|---|---:|---:|---:|---:|
| V-JEPA 2.1 | 12/12 | 12/12 | 1,945.45 ms | 1,989.73 ms |
| DINO-WM Flood-SAR adaptation | 12/12 | 12/12 | 38.48 ms | 47.57 ms |

Latencies are descriptive post-warm-up, batch-one wall-clock measurements from an
NVIDIA H100 environment. The input-sensitivity counts establish that aligned
inputs did not collapse to the static or shuffled outputs; they are not predictive
accuracy measurements.

## TRACE evidence smoke

For both backends, one delivered observation was verified, processed by the
learned model, persisted with model and checkpoint provenance, and attached to a
TRACE record during a wait-enabled development plan cycle. The authoritative
TRACE decisions and selected operational action-event signature matched the
surrogate-only baseline. The trace-record chain verified successfully, and the
learned output remained `used_for_trace_gate=false`.

The V-JEPA smoke recorded total service time of `2,322.60 ms`. The DINO-WM smoke
recorded `385.77 ms`. These single-run values demonstrate the instrumented path
and are not distributional latency estimates.

## Limitations

The qualification does not measure prediction error, calibration, mission
outcomes, safety, or learned-model superiority. It does not rerun RQ1-RQ4 and does
not evaluate RQ5. The results support a narrow implementation claim: two learned
visual-model families can produce integrity-checked, replayable, provenance-bound
supporting evidence through the same TRACE integration boundary while the frozen
surrogate remains authoritative.

Exact machine-readable reports and their checksums are in
[`worldmodel_live_support/`](worldmodel_live_support/).
