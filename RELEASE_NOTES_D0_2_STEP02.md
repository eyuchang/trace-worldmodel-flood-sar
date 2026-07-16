# D0.2 Step 2 Release Notes: Safe Delivery, Alert Semantics, and Animated Assets

This increment closes three review findings that remained after route-safe navigation.

## What changed

- Reaching a stranded group is now **pickup**, not rescue completion.
- The boat boards people, then waits for a separately TRACE-gated `evacuate_to_safety` commitment.
- Evacuation follows graph-valid waterway segments to the declared Safe Transfer Dock.
- People count as rescued only after unloading and handoff at the safe location.
- The default post-rescue disposition is `standby_at_safe_location`; the controller may retask the boat later.
- The Riverside Safe Transfer Dock is co-located with the Rescue Base, so standby there also looks like a return to the starting area.
- The emergency-call form now distinguishes a current waiting total from additional people.
- Same-location calls update one incident marker, while a small badge records the number of alerts received.
- Waiting, onboard, and delivered counts are represented separately.
- The boat displays an onboard passenger badge during evacuation.
- The web map uses recognizable animated SVG boats and drones, with heading rotation, smooth translation, rotor motion, boat bobbing, and wake animation.

## TRACE behavior

The outbound dispatch record licenses only travel to the pickup. After boarding, the Mission Controller creates a new evacuation candidate. Each candidate route to safety receives its own prediction, typed evidence, TRACE record, consumer decision, and authority check. Pickup therefore cannot silently authorize the return leg.

## Validation

```text
33 tests passed
JavaScript syntax check passed
Python compile checks passed
```

The lifecycle regression test verifies:

```text
outbound dispatch
  -> boarding
  -> pickup (rescued_people remains 0)
  -> TRACE-gated evacuation
  -> unloading
  -> safe delivery
  -> standby
```

## Not yet implemented

- continuous background drone coverage and interrupt/resume;
- a safe transfer site on a separate waterway branch;
- dependency-indexed operational bindings;
- proactive hydrology-based clearance expiry;
- photorealistic or WebGL 3D rendering;
- learned V-JEPA prediction.
