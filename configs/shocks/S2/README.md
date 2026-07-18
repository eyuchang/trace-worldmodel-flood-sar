# S2 shock registries

The Day 1 R-B development registries explicitly contain no shocks. They bind
each development seed to an auditable empty schedule instead of treating shock
absence as an undocumented runner default. R-C schedules are intentionally not
created until E7/G3 decides their role and parameters.

Registry files are strict `trace-shock-registry-v1` YAML. Runners must validate
the registry seed and regime, retain the validated registry hash, and never
sample shocks dynamically.
