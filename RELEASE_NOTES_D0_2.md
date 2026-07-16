# D0.2 Release Notes: Route-Safe Navigation and Visible Re-evaluation

D0.2 is the first corrective increment after the D0.1 plumbing prototype.
It addresses two concrete defects found during review:

1. a rescue boat could appear to travel across non-navigable space; and
2. S1-S5 changes did not expose the reasoning chain or the TRACE records that changed.

## What changed

- Added a route-constrained navigation graph over waterway edges.
- Added `PathSegment` with route ID, edge index, direction, endpoints, and mode.
- Boat movement now follows waterway edge geometry only.
- If the boat changes routes while away from base, it first returns along graph edges to a junction.
- A newly blocked edge interrupts motion at the edge boundary instead of allowing the boat to cross.
- Added reasoning-cycle events for material S1-S5 changes:
  trigger -> state -> prediction -> claim -> TRACE -> plan -> commitment.
- Added explicit TRACE semantic revisions after parameter or state changes.
- Redesigned the browser layout around one operational map, one decision banner,
  one reasoning panel, and tabbed TRACE/event/metric detail.
- Added controller/truth/difference views with closed-edge rendering.

## What is still not implemented

- continuous background drone coverage and interrupt/resume;
- hydrology forecast ensembles and proactive clearance expiry;
- dependency-indexed operational bindings between records and commitments;
- value-of-information reconnaissance scheduling;
- the actual V-JEPA encoder and learned action-conditioned predictor.

Those are the next increments. D0.2 remains a research simulator with a transparent surrogate model.
