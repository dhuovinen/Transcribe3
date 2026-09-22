# Progress

## Current work

Completed external-drive recording archival with a dedicated admin screen. The archive
keeps transcript/session metadata local and moves only original audio after a verified
copy to the configured archive folder.

## Last known-good state

Before this change, audio uploads are stored in `sessions/<session-id>/` alongside
`session.json`; the API and UI test suites are present and unmodified for this work.

## Next steps

The archive folder is configured at `/Volumes/Extreme SSD/Transcribe3 Archive` and the
live UI confirms it is connected with 919.3 GB free space. The combined unit and API
suite has 130 passing tests; the production frontend build passes. The broader suite's
existing CLI unsupported-format test attempts a live model request and exceeds the
30-second command window, unrelated to archive behavior.

The Archive administration page now documents the difference between Archive copy and
Offload immediately above the recordings table; the frontend production build passes.
