# Convergence workbench

Open `/#convergence` or select Convergence testing in the workspace sidebar.
Start the local FastAPI backend separately using the [backend instructions](../../../backend/README.md).

## Configuration and sync

All ten documents are loaded from the backend, including
`backend/fixtures/convergence_run_settings.json`. Valid edits autosave after 600 ms.
Fields and JSON edit one draft. Backend validation is authoritative; invalid
drafts stay visible and are not written to disk. The backend detects external
changes by polling file content hashes every second and notifies the UI via SSE.

Clean editors refresh automatically. Dirty editors show both versions when the
file revision changes. Reload discards the browser edits; Keep my draft explicitly
allows saving against the latest revision. A further external change still
rejects that save. Unsaved drafts and conflict markers are cached in browser
storage for recovery; backend files remain authoritative for clean documents.
Drafts from the earlier frontend-only v1 cache are not automatically applied.

Preview uses the backend's execution prompt renderers, including the appended
output schema. Starting a run requires a validated preview, all documents synced,
server-side credentials, and explicit confirmation of billable calls. No API keys
are collected by the frontend. Export setup downloads the draft document strings.
Reset document restores the build-time bundled baseline and autosaves it to its
local source file after validation.

## Runs

One backend-owned batch runs at a time. Inputs and exact rendered messages are
frozen when the batch starts; subsequent edits affect the next batch only.
Closing the tab does not stop a run. Stop finishes an already in-flight call and
checkpoints it before stopping; there are no automatic retries or resumes.

Results show Q traces and active-only running means, box plots with every active
observation, cumulative coverage, ddof=1 summary statistics, the Q matrix, complete
assessments, P/Q matrices, raw responses, frozen inputs and the execution log.
Click a chart point or matrix row to select a response. Missing Q is never zero.
Run history includes incomplete and legacy notebook batches; missing legacy
provenance is labelled unavailable rather than reconstructed.

Use `npm run build` for TypeScript and production build validation. The
convergence backend tests are in `backend/tests/test_convergence.py`; they use
temporary files and stub clients, not live LLM calls.
