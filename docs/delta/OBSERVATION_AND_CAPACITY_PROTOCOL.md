# Observation and capacity protocol

## Latent truth and lossy evidence

Latent incidents are sampled from physical hazard, exposure, and vulnerability.
They are not sampled from the desired call schedule. The observation channel is
applied afterward and supports non-reporting, first reports, duplicates,
multi-channel reports, revisions, callback failures, dropped calls, third-party
welfare checks, false benign levee reports, and location noise.

At `iota=0.9`, expected reports are calibrated analytically to hourly arrivals
`[3, 5, 7, 12, 8, 5]`. The calculation subtracts uniform expected false reports,
conditions on the physical-hazard-derived latent rate, solves reporting and
extra-report probabilities, and accounts for expected delay spill into the next
hour. A unit test reconstructs the six expectations to numerical tolerance.

Artifacts are separated into:

- controller-visible raw calls;
- controller-derived belief relationships/revisions;
- hidden truth lineage used only after runtime for scoring.

The runtime has no lineage argument. Deleting lineage yields byte-identical
public decisions, evidence, TRACE records, commitments, and outcomes.

## Offline evaluation metrics

The registered report provides means or Wilson 95% intervals for total/hourly
calls, non-reporting, relationship fractions, callback failure, dropped calls,
location error, reconciliation accuracy, false-report outcomes, and operation
counts. These intervals describe synthetic seed variation, not population or
field uncertainty.

For the untouched `confirmatory-v5-primary`:

- duplicate fraction: 0.0752 (95% CI 0.0673–0.0840);
- multi-channel fraction: 0.0436 (0.0376–0.0505);
- revision fraction: 0.1346 (0.1242–0.1458);
- false-report fraction: 0.1185 (0.1087–0.1291);
- callback-failure fraction: 0.1102 (0.1007–0.1205);
- non-reporting fraction: 0.0532 (0.0451–0.0626);
- mean location error: 179.42 m;
- scored reconciliation accuracy: 0.8476 (0.8250–0.8677).

## Incident requirements and resource capabilities

The versioned tables live in the hashed population/resource parameter artifact.
Each incident declares one required capability, initial-response duration, and
service units. Each resource declares capabilities, base, route, activation,
staging, travel, availability, service duration, and service units.

The v2 `kappa=0.5` inventory is one local rescue boat and Type I engine plus a
preauthorized Rio Vista Zodiac rescue boat and Type I engine staged at T+5,400
seconds. The boats support water rescue and missing-person search. The engines
support medical, road rescue, welfare checks, and levee inspection. Engines are
ineligible for water rescue. `service_units=2` is a normalized analytical
capability/load unit; each physical resource still permits one concurrent online
commitment.

## Demand/capacity definition

### Headline: gross compatible scenario load

At each 15-minute grid time:

1. select ground-truth incidents whose declared service interval is active;
2. group required service units by capability and required crossing route;
3. include scheduled, mobilized, reachable resources whether free or committed;
4. assign each resource to at most one compatible capability/route bucket;
5. maximize actually coverable service units without exceeding bucket demand;
6. divide total active demand by gross compatible capacity.

This metric is calculated before policy execution and is identical under Toy,
MLP, V-JEPA, or other policy choices at fixed scenario inputs.

### Secondary: residual operational pressure

After TRACE execution, active authorized commitments remove the truth demand
they cover. Only free, mobilized, reachable, compatible resources count against
remaining demand. A false-report commitment consumes its physical resource but
does not erase truth demand. Hidden lineage is used only in this offline
aggregate evaluation; no truth identifier appears in the public windows.

Empty demand has ratio zero. Positive demand with zero compatible capacity is
explicitly unserviceable and has no fabricated finite denominator.

## Registered gate result

The v2 book gross load is 1.5. The untouched confirmatory-v5 median is 1.5
(bootstrap 95% CI 1.333–1.5), satisfying the preregistered median point-estimate
band `[1.4, 1.6]`. The older v5 local-only/hybrid result of 3.0 remains preserved
as adverse evidence. It is not recomputed or relabeled under the v2 definition.
