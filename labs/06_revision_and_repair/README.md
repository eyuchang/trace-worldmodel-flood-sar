# Lab 6 - Surprise, revision, and localized repair

## Goal

Close the loop after the world contradicts a model-conditional prediction.

## Tasks

1. Execute one admitted short action prefix.
2. Store the realized observation as new evidence.
3. Compare predicted and realized mission predicates.
4. Create a revision that cites the original record.
5. Traverse claim-to-commitment links to identify dependent branches.
6. Replan only those branches and preserve unaffected commitments.
7. Re-run repository verification.

## Commands

```bash
pytest tests/test_end_to_end.py
trace-jepa-demo --output artifacts/runs/lab06
```

## Exit test

The old forecast remains readable, the revision is attributable, the repair is local, the new commitment cites a new record version, and the append-only chain verifies.
