# YouTube Metadata Draft

## Title

Should We Send a Rescue Unit? Build a TRACE Flood Search-and-Rescue Controller

## One-sentence description

Follow a simulated flood call from evidence to TRACE, then write the Python
controller that allocates a response unit, refuses with a reason, and preserves
later corrections.

## Full description

A welfare-check call arrives during a simulated flood. The information may be
ready to use—but is a suitable response unit actually available?

This beginner-friendly code lab explains the system from the ground up:

- **Search and rescue (SAR):** coordinating limited response units to reach
  people who may need help;
- **TRACE:** the decision notebook that records whether the available
  information may move forward; and
- **your controller:** the code that checks available units and returns an
  allocation or a refusal.

You will run and replay the supplied flood scenario, walk through four completed
decisions, implement three focused Python functions, pass fast tests, and try
two resource “what if?” examples.

By the end, you will be able to explain:

- why TRACE `CLEAR` allows a resource check but does not send a unit;
- the difference between an information refusal and a capacity refusal;
- how deterministic resource ordering makes decisions repeatable; and
- why later information is appended as a repair instead of erasing history.

Requirements: the prepared student workspace and Python environment. No GPU,
model download, flood video, or live data connection is required. The lesson
uses a simulated flood-response scenario.

Repository and workshop links should be added only after the reviewed materials
are published. Do not insert private links or local computer paths.

## Suggested chapters

See [`chapters_and_captions.md`](chapters_and_captions.md). The review draft is
14 minutes 50 seconds.

## Thumbnail concept

A 16:9 dark navy card with one large question:

```text
A FLOOD CALL ARRIVES.
SHOULD WE SEND A UNIT?
```

Under it, show one simple path:

```text
TRACE CLEAR -> CHECK RESOURCES -> ALLOCATE or REFUSE
```

Use large white text, cyan for TRACE, green for allocate, and amber for refuse.
Do not use emergency-agency seals or real disaster photography.

## Upload state

Draft only. No upload, publication, account access, comments, monetization, or
visibility setting has been performed.
