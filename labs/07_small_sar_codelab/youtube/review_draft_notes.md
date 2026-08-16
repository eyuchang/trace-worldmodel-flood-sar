# Review Draft Notes

`review_draft.mp4` is a locally generated, screen-only, silent review artifact.
It contains title cards, exact terminal commands and outputs, exercise logic,
scope statements, and burned-in explanatory text. `review_draft.en.srt` carries
condensed chapter narration for reviewers who want timed text. The complete
captions-ready narration is in `recording_script.md`.

The draft intentionally contains:

- no microphone or camera recording;
- no personal account, username, hostname, or home-directory path;
- no external footage, logo, music, or copyrighted image;
- no network or browser session; and
- no upload metadata or publication action.

It is designed to let Dr. Chang review pacing, sequence, commands, expected
outputs, and scientific wording before anyone records personal narration. It is
not the polished final YouTube upload.

To rebuild locally, use `build_review_draft.py` with an explicit new output
path. The builder requires Pillow and FFmpeg and refuses to overwrite files.
