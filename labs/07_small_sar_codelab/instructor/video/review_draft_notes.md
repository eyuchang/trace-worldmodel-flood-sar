# Review Draft Notes

`review_draft.mp4` is a locally generated, screen-only, silent **visual
preflight**. It previews the actual recording sequence: README, BYOD setup,
terminal, editor, focused tests, student-result output, capacity comparison,
and replay.
`review_draft.en.srt` carries condensed chapter narration for
reviewers who want timed text. The complete captions-ready narration is in
`recording_script.md`.

The draft intentionally contains:

- no microphone or camera recording;
- no personal account, username, hostname, or home-directory path;
- no external footage, logo, music, or copyrighted image;
- no browser account or network session; and
- no upload metadata or publication action.

It is designed to let Dr. Chang review the novice learning progression,
screen sequence, commands, definitions, code visibility, and expected outputs
before anyone records personal narration. Each TODO screen represents the
same-file pause-and-reveal sequence in the recording script; the private reveal
tool itself is never shown. This is not the polished final YouTube upload or a
substitute for the real code-along capture.

To rebuild locally, use `build_review_draft.py` with an explicit new output
path. The builder requires Pillow and FFmpeg and refuses to overwrite files.
