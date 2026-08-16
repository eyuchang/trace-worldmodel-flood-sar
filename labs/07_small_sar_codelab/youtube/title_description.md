# YouTube Metadata Draft

## Title

Build an End-to-End TRACE Flood-SAR Controller in One Lab

## One-sentence description

Run the deterministic TRACE Small Flood-SAR simulator, implement the controller
that separates evidence authorization from resource allocation, append a
visible-evidence repair, and verify exact replay—without a GPU or model download.

## Full description

This student code lab uses the delivered `WF-DFLD-01-SMALL` synthetic Flood-SAR
teaching simulator. You will run a fresh scenario, inspect controller-visible
TRACE records, implement deterministic rescue allocation/refusal logic, preserve
append-only repair history, and replay the committed book byte-for-byte.

The lab requires Python and a prepared repository checkout. It does not require
a GPU, learned-model checkpoint, flood video, live external data, debate module,
or regret implementation.

Learning objectives:

- distinguish latent world state from controller-visible evidence;
- distinguish TRACE verdicts, TRACE consumer actions, and resource commitments;
- implement compatible-resource filtering and deterministic dispatch;
- explain evidence refusal versus CLEAR-without-capacity refusal;
- append a repair without erasing the prior decision; and
- explain what deterministic replay proves and what it does not.

Scientific scope: Small is a deterministic, headless, synthetic, reduced-order
teaching simulator using simulation-grade geography. Teaching variants are not
registered experiments or operational emergency-response evidence. The retained
book evidence is an authorized artifact-reconstruction replication after
earlier artifact-retention failures.

Repository and workshop links: add only after the reviewed materials are
published. Do not insert a private repository, local path, or personal account.

## Suggested chapters

See [`chapters_and_captions.md`](chapters_and_captions.md). The review draft is
14 minutes 50 seconds.

## Thumbnail concept

A 16:9 dark navy card with a three-stage horizontal path:

```text
TRACE CLEAR  →  CAPACITY CHECK  →  COMMITMENT
                         ↘ NO CAPACITY: REFUSE
```

Use large white text, cyan for TRACE, green for commitment, and amber for the
capacity refusal. Include a small “NO GPU” badge. Do not use emergency-agency
seals, real disaster photography, or imagery that could imply operational use.

## Upload state

Draft only. No upload, publication, account access, comments, monetization, or
visibility setting has been performed.
