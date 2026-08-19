# Review Draft Notes

`review_draft.mp4` is a locally generated, screen-only, silent **visual
preflight**. It is only an internal layout check, not the student-facing video
or a recommended review asset. Record the real narrated code-along from the
single `recording_script.md` guide instead.
`review_draft.en.srt` carries condensed chapter narration for
reviewers who want timed text. The complete captions-ready narration is in
`recording_script.md`.

The draft intentionally contains:

- no microphone or camera recording;
- no personal account, username, hostname, or home-directory path;
- no external footage, logo, music, or copyrighted image;
- no browser account or network session; and
- no upload metadata or publication action.

Each TODO screen represents the same-file pause-and-reveal sequence in the
recording script; the private reveal tool itself is never shown. This is not
the polished final YouTube upload or a substitute for the real code-along
capture.

To rebuild locally, use `build_review_draft.py` with an explicit new output
path. The builder requires Pillow and FFmpeg and refuses to overwrite files.
