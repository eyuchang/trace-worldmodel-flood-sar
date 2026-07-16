# Lab 1 - Mission briefing, contracts, and append-only history

## Goal

Understand the operational cast, render the two knowledge views, and create the first immutable evidence and TRACE records.

## Briefing

- The Flood Environment owns hidden truth.
- The survey drone and rescue boat are physical agents.
- The Mission Controller is the one central program.
- The Planner, World Model, TRACE Gate, and Action Dispatcher are modules inside that program.
- The Incident Commander supplies external authority.
- Offline evaluation happens after the episode.

## Tasks

1. Read `docs/MISSION_BRIEF.md` and `docs/TRACE_RECORD_WALKTHROUGH.md`.
2. Run `trace-jepa-visualize --output artifacts/runs/lab01_brief`.
3. Explain why `mission_controller_knowledge.svg` omits the debris obstruction.
4. Inspect `ActionInstance`, `WorldModelEvidence`, `TraceRecord`, `Commitment`, and `RealizedOutcome`.
5. Write one evidence object and one TRACE record.
6. Verify idempotent writes and the repository hash chain.
7. Tamper with a disposable log and confirm verification fails.

## Exit test

A student can name every operational entity, distinguish reported knowledge from hidden truth, and serialize a record without losing a field.
