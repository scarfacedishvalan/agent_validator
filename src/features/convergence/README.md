# Convergence workbench

Open `/#convergence` or select Convergence testing in the workspace sidebar.
Start the local FastAPI backend separately using the [backend instructions](../../../backend/README.md).

## Configuration and sync

All twelve documents are loaded from the backend, including
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

Run settings store `models` (the editable dropdown choices, as `openai:model`
identifiers) and `model` (the selected choice used by execution). Both use the
same file-sync path; selecting a model never creates a separate UI-only value.
The selection must remain in the list. The initial reasoning choices are GPT-6
Astra, GPT-5.6 Terra and GPT-5.6 Luna, as listed in OpenAI's
[reasoning guide](https://developers.openai.com/api/docs/guides/reasoning).
The existing GPT-4o selection is preserved and labelled non-reasoning. This list
is configurable, not an account-specific availability check. Temperature is not
configurable in convergence runs; the backend omits the parameter. Remove it
from any recovered old run-settings draft.

Model pricing is a separate file-backed setup document,
`backend/fixtures/model_pricing.json`, editable in Fields or JSON. Standard USD
rates per million tokens and their source/date are frozen with each new run.

In Setup, open **Evidence snapshot** to select, preview and load an example from
`backend/fixtures/evidence_examples.json`. Confirming replacement copies the whole
example into the active evidence snapshot and autosaves it, replacing any current
evidence edits. Conflicts must be resolved first. The **Evidence examples**
document lets you edit/add examples in Fields or JSON with the same local-file
sync. Scenarios are synthetic, not historical observations or expected answers;
all bundled examples and the active default supply 1-, 3- and 12-month returns
for HML, RMW and MOM. Weak-mixed and observed-flat scenarios replace the former
sparse/empty examples. Flat returns are synthetic observations, not missing values.
Custom snapshots may still omit unavailable observations without imputation.
Editing the library does not alter the active snapshot until explicitly loaded.
Existing batches retain their frozen evidence.

The bundled q convention is the subjective conditional arithmetic mean of the
cumulative return over the next 12 months on the same defined factor spread,
expressed as a decimal, unannualized, and before benchmark adjustment. It is not a
median or most-likely scenario. "Absolute" means a standalone
factor-level view; it does not define total versus excess returns. This output is
not automatically a Black-Litterman-ready input. Bundled 1-, 3-, and 12-month inputs are synthetic trailing
cumulative returns; their windows overlap. The model does not convert historical
returns into q or subtract a benchmark. If the downstream optimizer needs excess
returns, define and apply a separate deterministic benchmark conversion.

## Runs

One backend-owned batch runs at a time. Inputs and exact rendered messages are
frozen when the batch starts; subsequent edits affect the next batch only.
Closing the tab does not stop a run. Stop finishes an already in-flight call and
checkpoints it before stopping; there are no automatic retries or resumes.

Results show Q traces and active-only running means, box plots with every active
observation, cumulative coverage, ddof=1 summary statistics, the Q matrix, complete
assessments, P/Q matrices, raw responses, frozen inputs and the execution log.
They also show estimated USD cost per attempted iteration and the total of
available estimates. A collapsed metadata JSON section at the end contains token
usage, frozen pricing and cost breakdowns. Cached reads/writes are priced separately;
reasoning tokens are already included in output counts. Missing usage/prices and
unsupported pricing conditions are explicitly unavailable rather than zero.
Old runs are not repriced using today's rates.
Click a chart point or matrix row to select a response. Missing Q is never zero.
Run history includes incomplete and legacy notebook batches; missing legacy
provenance is labelled unavailable rather than reconstructed.

Use `npm run build` for TypeScript and production build validation. The
convergence backend tests are in `backend/tests/test_convergence.py`; they use
temporary files and stub clients, not live LLM calls.
