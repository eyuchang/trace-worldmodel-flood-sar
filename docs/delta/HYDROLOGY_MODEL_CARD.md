# Reduced-order hydrology model card

## Purpose and non-purpose

The Small physical layer generates a deterministic, auditable teaching signal
that can affect observations, access beliefs, and TRACE evidence. It is not a
hydrodynamic, hydraulic, meteorological, or CDEC forecast and has not been
calibrated to the 1972, 1980, or 2004 events.

## Inputs and units

The five-minute meteorology series emits rain (milli-inches/hour), wind
(milli-knots), ceiling (feet), and an aviation-operability flag. Coefficients are
frozen in `physical_parameter_table()` and included as a hashed artifact.

For every gauge and tick, stage in millifeet is exactly:

```text
baseline + M2 tide + runoff response + wind setup + upstream release
```

The M2 period is 12 hours 25 minutes (44,700 seconds). Each gauge has an explicit
baseline, phase, amplitude, and lag. Additive components are separately emitted,
and schema validation rejects a stage that does not equal their integer sum.
The upstream-release component is retained as a declared reduced-order term; it
must not be interpreted as an agency release forecast.

## Geography and state coupling

Crossing and road state are emitted at every physical tick. Small is breach-free
and both crossings are expected to remain open, but generated weather and stage
still affect travel-time friction and confidence. Predictor evidence and
resource mobilization consume this generated state; neither route status nor
travel duration is hard-coded in the controller.

Truth also emits time-varying structure flood/access state and levee seepage
condition. These are causal teaching states only.

## Validation and limits

Automated checks cover units, the additive identity, deterministic output,
M2-period configuration, gauge identity/threshold status, crossing-state
coverage, causal `sigma` response, and invariance of physics to non-hazard axes.

Known limitations include no 2D flow, no breach inflow, no tidal reversal
hydraulics, no channel routing calibration, no soil/infiltration calibration,
no uncertainty ensemble, and no comparison to observed stage time series.
Generated values must be described as synthetic stage signals, never CDEC
predictions.
