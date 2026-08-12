# WF-DFLD-01-REFERENCE capacity protocol v1

## Status and claim boundary

This document records the development implementation of approved decision D4.
It does not introduce a numerical load gate. The values produced by this
evaluator are descriptive integration results from a synthetic teaching
scenario; they are not estimates of emergency-system capacity or readiness.

Capacity is evaluated offline only after the mission runtime completes. The
evaluator may read hidden truth and hidden resource state; no truth identifier
is serialized into the aggregate capacity artifact and no online decision may
read the result.

## Registered grid and active demand

The evaluator samples `[T+0, T+96 h)` every 900 seconds, for exactly 384
windows. A truth incident is active at `t` when
`onset_s <= t < scheduled_resolution_s`. Active demand is the sum of its
declared normalized analytical service units. Incident resolution times remain
causal scenario outputs and are not altered to obtain a load value.

## Primary strict concurrent capacity

A physical resource can cover an incident only if all of the following hold:

- its declared capability includes the incident requirement;
- its service units are at least the incident's complete requirement;
- its activation schedule has reached `available`;
- the latest hidden state has an on-duty crew, no initial outage or crew-rest
  state, and positive fuel/charge;
- the registered route is model-reachable at that sample, with open modeled
  crossings for road routes and normal modeled operability for air routes; and
- any represented single-resource constraint is satisfied.

The matching assigns each physical resource to at most one active incident and
each incident to at most one resource. It maximizes covered incident service
units. The implementation uses the weighted greedy algorithm for a transversal
matroid, with deterministic augmenting paths and identifier tie breaks. An
exhaustive test verifies the implementation over every compatibility graph with
three incidents and three resources.

The strict ratio is `active demand / strict matched capacity`. Zero demand
returns zero. Positive demand with zero strict capacity returns a null finite
ratio plus an explicit unserviceable flag; it is never converted to zero or an
invented denominator.

## Sensitivity measures

Two non-primary measures are reported beside strict concurrency:

- **Uncapped compatible service-unit capacity** counts each otherwise eligible
  resource's analytical service units once if it can reach at least one active
  compatible incident. It is not capped by demand.
- **Historical normalized coverable load index** treats analytical service
  units as divisible across capability/island demand buckets, caps them at
  bucket demand, and maximizes the resulting unit flow. This is intentionally
  not a physical concurrency claim. It exists to retain a transparent
  normalized sensitivity comparable to protocol history.

For every window, strict matched capacity is no greater than the historical
divisible capped capacity, which is no greater than uncapped compatible units.

## Commitments and residual pressure

The evaluator joins an allocated call to hidden truth only after runtime through
the hidden lineage artifact. A commitment covers truth demand only when its
selected physical resource was compatible, available, and model-reachable at
authorization time. Allocations responding to false reports consume their
physical resource but cover no truth demand. Multiple commitments for one truth
incident do not multiply covered demand.

Every allocation remains busy until its untruncated scheduled completion. A
successfully completed compensation ends that busy interval at the compensation
time; failed compensation does not. Residual demand excludes truth incidents
covered by active valid commitments. Free strict capacity excludes every busy
physical resource, including resources committed because of false or
misreconciled evidence.

## Current modeled constraints and limitations

The route calculation consumes the simulation topology, crossing state, and air
operability. Explicit wind ceilings for UAS and rotary assets are enforced.
Swiftwater teams that require paired watercraft/access are not counted as
single-resource strict capacity. Flood-fight crews that require material supply
are not counted for hazard-control unless that dependency is represented; they
may still satisfy levee-inspection demand.

The current physical state does not expose continuous roadway water depth or a
separate daylight field. Road accessibility is therefore represented by the
versioned crossing/access topology, and the rescue-boat night-capability note is
not converted into an unsupported operational rule. The ambulance hospital leg
is outside this incident-response-initiation load measure. These limitations
must remain visible in any result interpretation and should be revisited before
a later operational-effectiveness study.
