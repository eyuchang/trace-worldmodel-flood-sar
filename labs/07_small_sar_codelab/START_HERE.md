# Start Here: Your Flood-Response Mission

A welfare-check call has arrived during a simulated flood. The information may
be good enough to use—but should the system actually send a response unit?

That is the decision you will program.

## The whole lab in one picture

```text
CALL -> EVIDENCE -> TRACE -> YOUR CONTROLLER -> ALLOCATE or REFUSE
                           \
                            later information -> append a REPAIR
```

- **TRACE** is the decision notebook that says whether the available
  information may be used now: `CLEAR` or `HOLD`.
- **Your controller** checks whether a suitable, reachable response unit is
  available.
- An **allocation** selects a unit. A **refusal** selects none and records why.
- A **repair** adds a later correction without erasing the earlier decision.

No search-and-rescue or TRACE background is required. The full lesson explains
every term before you use it.

## Your route

1. Read [Meet the system](README.md#meet-the-system).
2. Run the setup preflight.
3. Run the flood simulation and completed walkthrough.
4. Implement three TODO functions.
5. Pass the tests and run your controller.
6. Try two resource “what if?” examples and replay the scenario.

## First command

Work from the repository root. If your instructor prepared `.venv`, run:

```bash
.venv/bin/python labs/07_small_sar_codelab/scripts/preflight.py
```

Wait for five PASS lines and `READY`.

Then open the [full guided tutorial](README.md). Do not jump directly to the
TODOs: the walkthrough first shows what the inputs mean and why the controller
needs three different outcomes.
