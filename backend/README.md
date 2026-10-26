# Agent Experiment Workbench API

Run from this directory on Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

The API listens at `http://127.0.0.1:8000`; interactive OpenAPI docs are at `/docs`. The React workbench connects to this local API by default. On first use it creates the illustrative sample evidence snapshot if the database is empty.

### Restart backend and frontend together (Windows)

Double-click `restart-dev.cmd` in the project root to launch both services.
The launcher keeps its window open so you can read success or error output.
It also forwards arguments, for example `restart-dev.cmd -WhatIf` for a dry run.
When launched from Explorer, credentials must already be available in its
environment; otherwise launch from a terminal where `OPENAI_API_KEY` is set.

From PowerShell:

```powershell
Set-Location C:\work\agent_validator
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\restart-dev.ps1
```

The script activates `C:\work\hackathon\.venv` in both service windows, switches
to the correct working directories, stops listeners on ports 8000 and 5173
(including a backend Uvicorn reload supervisor), and starts both services in
separate persistent PowerShell windows. It checks backend health and frontend HTTP
readiness. Set `OPENAI_API_KEY` in the calling terminal first so both windows
inherit it; the script does not read or print credentials.

Use `-WhatIf` to validate prerequisites without stopping or starting anything.
Override the environment with `-VenvPath 'C:\path\to\.venv'`. Dependencies must
already be installed; the script does not install them. A readiness failure leaves
the windows open for diagnosis and exits with an error.

**Warning:** any process listening on these ports is in scope for termination,
even if unrelated to this project. Active convergence calls are forcibly
interrupted; only already-saved checkpoints are retained. Review the ports before
running, or use `-Confirm` for an additional confirmation prompt.

SQLite is created at `backend/data/workbench.sqlite` by default. Set `AGENT_VALIDATOR_DB_PATH` to use another local path. The metric catalog is loaded from `backend/fixtures/metric_definitions.json`. The Convergence testing UI can edit this shared file; the mutation API reads the updated catalog on subsequent requests.

Factor definitions are kept separately in `backend/fixtures/factor_definitions.json`. The output schema and example live in `backend/fixtures/factor_view_output_contract.json` and can be loaded with `app.services.factor_view_prompts.load_factor_view_output_contract()`. Active templates are `backend/prompts/system_prompt.txt` and `backend/prompts/user_prompt.txt`, with shared grounding rules in `backend/prompts/shared_financial_grounding_policy.txt`.

Render client-ready messages with `app.services.factor_view_prompts.render_factor_view_system_prompt(...)` and `render_factor_view_user_prompt(...)`. Pass the returned strings as the system and user message content; both take the target horizon, return convention, bounds, factor definitions, and metric definitions, while the user renderer additionally takes the evidence snapshot.

Default prompt runtime values are in `backend/fixtures/factor_view_defaults.json` (`target_horizon`, `q_return_convention`, `q_min`, and `q_max`). An orchestrator can load this single JSON file and override any values before calling the prompt renderers. `null` bounds mean no configured lower or upper bound.

An AISuite-backed factor-view orchestrator is available as `app.services.orchestrators.factor_view_orchestrator`. From the repository root, set `OPENAI_API_KEY` and run `python run_factor_view_orchestrator.py`; it uses `backend/fixtures/evidence_snapshot_example.json` by default. Alternatively, from `backend`, run `python -m app.services.orchestrators.factor_view_orchestrator`. Pass `--snapshot <path>` and optionally `--model openai:<model>` to use another snapshot or model. The orchestrator includes the output schema in the system message and validates the returned JSON and matrix alignment. Its `tools` parameter is reserved and currently unused.

The orchestrator CLI prints only `P` and `Q` as JSON, with each `P` row on its own line and all of `Q` on one line; `generate_factor_views()` still returns the full validated response.

Select a behavioral persona using `generate_factor_views(snapshot, personality_key="Contrarian Mean-Reversion Analyst")` or CLI option `--personality "Contrarian Mean-Reversion Analyst"`. The value must be an exact key in `backend/fixtures/personalities.json`; the default is `"Trend-Following Analyst"`. Instructions are inserted into the user prompt and remain subordinate to the shared financial grounding policy and system constraints. Invalid keys or malformed selected instructions fail before the LLM call.

Run the backend tests from this directory:

```powershell
py -m unittest discover -s tests -v
```

## Repeated-view diagnostics

Open `../factor_view_convergence.ipynb` from the repository root to compare repeated calls on identical evidence. Install `../notebook-requirements.txt` into the selected notebook kernel if needed. Configure the call count, personality key, model, and snapshot before running the live-call cell. Set `OPENAI_API_KEY` securely in the kernel environment.

The plots show individual Q estimates, active-only running means and distributions, and cumulative active-view fractions for every catalog factor. Abstentions remain missing, never zero; full responses remain available for inspecting rationales. Live calls incur API costs, and errors stop the batch without silently skipping or retrying failures. These diagnostics assess repeatability, not forecast accuracy or proof of convergence.

Each batch saves a single uniquely named JSON under `convergence_results/` (excluded from Git). It includes every full response and the experiment inputs, with an atomic checkpoint after each successful iteration. Check `complete` and the requested/completed iteration counts before treating a saved batch as finished. Configure `OUTPUT_DIR` in the notebook or pass `output_path` to `collect_runs()`; an existing output file is rejected rather than overwritten.

## Convergence testing UI and API

New batches persist an extensible `metadata` JSON object in every result
checkpoint and export. The final, collapsed **Run metadata (JSON)** section in
Results shows the frozen selected model, provider response model/ID when available,
and per-attempt token usage, including cached/reasoning details when returned.
`tokenUsage.reportedTotals` sums provider-reported prompt, completion and total
tokens; cached and reasoning tokens are subsets, not added again. Totals cover
only available counts: `complete: false` marks missing usage, and entirely
unavailable counts are `null`, never estimated as zero. Failed validation still
records usage if the provider returned it. Provider errors without usage cannot
be counted; historical runs without metadata explicitly show it as unavailable.
The Results tab shows estimated USD cost per attempted iteration and a total of
available estimates. Rates come from editable `backend/fixtures/model_pricing.json`,
also available as the **Model pricing** setup document with normal file sync.
Rates, source and verification date are frozen at run start and saved under
`metadata.costs`, so later edits cannot reprice historical runs. Rates use standard
USD per million tokens; cached input is separated from uncached input and reasoning
tokens are not charged twice. Missing pricing/usage, unsupported service tiers,
cache writes without a configured rate and input above a configured context limit
produce an explicit unavailable estimate, not zero. These are token-only estimates,
not invoice amounts; no automatic web refresh or historical backfill is performed.
The seeded optional `cacheWrite` rate assumes standard 30-minute cache retention
(no retention override is sent by this client); adjust rates if that policy changes.

The React Convergence testing tab connects to `/api/v1/convergence`. Launch the
backend with the commands above and open `/#convergence` in the frontend.
Set `OPENAI_API_KEY` in the backend's environment before launching it. The existing
AISuite adapter uses OpenAI JSON mode; use `openai:<model>` identifiers with a
model that supports JSON mode. OpenAI SDK retries are disabled and each request
has a 120-second timeout. No LLM request is made by loading, editing or previewing
configuration; starting a batch requires explicit confirmation of billable calls.
Convergence settings no longer accept `temperature`; requests omit it and use
the provider default. Remove the field from any old unsaved run-settings drafts.

The output contract orders each assessment's fields as `factor`, `rationale`,
`status`, `q`, `confidence`, `evidenceRefs`, so the model writes its reasoning
before committing to a decision. Its example includes one abstention.

### Editable source files

The API exposes fixed document IDs rather than arbitrary filesystem paths:

| ID | Source |
|---|---|
| `run` | `backend/fixtures/convergence_run_settings.json` |
| `pricing` | `backend/fixtures/model_pricing.json` |
| `evidence` | `backend/fixtures/evidence_snapshot_example.json` |
| `examples` | `backend/fixtures/evidence_examples.json` |
| `personalities` | `backend/fixtures/personalities.json` |
| `defaults` | `backend/fixtures/factor_view_defaults.json` |
| `factors` | `backend/fixtures/factor_definitions.json` |
| `metrics` | `backend/fixtures/metric_definitions.json` |
| `system` | `backend/prompts/system_prompt.txt` |
| `user` | `backend/prompts/user_prompt.txt` |
| `policy` | `backend/prompts/shared_financial_grounding_policy.txt` |
| `contract` | `backend/fixtures/factor_view_output_contract.json` |

In **Setup -> Evidence snapshot**, select an example, inspect its JSON preview,
click **Load example**, then confirm **Replace evidence snapshot**. This copies
the whole snapshot into the active evidence file using the normal revision-checked
autosave flow. It replaces existing observations and unsaved evidence edits;
resolve any evidence file conflict first. The example library itself is unchanged.
The new library contains synthetic mixed, positive-trend, recent-reversal,
weak-mixed-signal and observed-flat-return scenarios, not historical data or expected
model answers. All bundled examples and the active default include 1-, 3- and
12-month returns for HML, RMW and MOM. Flat-scenario zeros are explicitly synthetic
observed returns, not missing-value replacements. Custom snapshots may still omit
unavailable observations; no automatic imputation is performed. Edit/add named
snapshots through **Evidence examples** or its local JSON file. Each entry uses the
same `name`, `asOf`, `values` shape as the active snapshot; metric references are
checked at preview/start. Edits to the library do not automatically change the
active evidence, and loading examples never changes a batch's frozen inputs.

Valid UI edits autosave after 600 ms. Writes compare the supplied SHA-256 revision
against the current file and use temporary-file replacement with flushing.
Stale writes return HTTP 409. External edits, deletions and editor-style atomic
replacements are detected using content hashes every second and reported via SSE.
Clean editors refresh; dirty editors require a reload/overwrite decision.
Independent external editors do not participate in the backend's write lock;
avoid saving the exact same file simultaneously in both editors.
Invalid external files remain visible with errors and block new batches, rather
than silently falling back to previous values. An invalid metric catalog does not
prevent starting the API so it can be repaired through the UI.

Document saves validate individual structure. Preview and start additionally
validate cross-document references, the selected personality, and template
placeholders. Templates must retain grounding policy and personality/evidence
placeholders. Output schemas are checked as JSON Schema and may use only local
fragment references; they cannot trigger remote schema downloads. Regardless of
the editable contract, core factor ordering, assessments, matrix alignment,
finite Q values, evidence references and configured Q bounds remain enforced.
Evidence snapshots stored in SQLite are separate from the file-backed evidence
input; mutation-builder changes do not silently overwrite that JSON.

### Routes

| Method | Route | Purpose |
|---|---|---|
| GET | `/config/documents` | Content, source path, revision and validation state; credential readiness only |
| PUT | `/config/documents/{id}` | Save `{content, revision}` or reject a stale/invalid edit |
| POST | `/preview` | Render `{documents: {id: content}}` through shared execution helpers |
| GET | `/events` | SSE change notifications, heartbeat and explicit sync errors |
| GET | `/runs` | Saved/active run summaries and unreadable-file issues |
| POST | `/runs` | Start using `{revisions: {id: revision}, confirmLiveCalls: true}` |
| GET | `/runs/{id}` | Full responses, provenance, progress and diagnostics |
| POST | `/runs/{id}/stop` | Finish/checkpoint the current call, then stop |

All routes in this table are relative to `/api/v1/convergence`.

### Execution and persistence

Use **one backend process/worker** per project. The in-process worker serializes a
batch's calls and allows one active batch at a time; there is no distributed job
queue. Closing the browser does not cancel it. Stop does not abandon an already
in-flight request. Graceful shutdown waits for that request and saves the
remaining partial batch. Restart marks previously running/stopping v2 files
`interrupted`; it never resumes billable calls automatically.

At start the backend snapshots every validated source document, its revision and
path, parsed runtime inputs and personality instructions, and exact system/user
messages. Each call uses that snapshot, never re-reading mutable files. Changes
while a batch runs apply only to the next batch. The CLI and notebook retain their
existing entry points and share prompt generation/response validation.

Each batch creates a unique `factor_views_<timestamp>_<uuid>.json`. The requested
results directory must be a subdirectory of the project. A local ignored index
at `backend/data/convergence_directories.json` retains directories used by API
batches so their history remains available after the configured directory changes.
History also discovers existing notebook files in the default/current directory.
Schema v2 adds lifecycle status, frozen inputs, messages, execution log and errors
while retaining notebook counts and full responses. Checkpoints are atomically
replaced after each validated response and when the batch stops/completes/fails.
Completion is exposed only after its checkpoint succeeds. A disk failure is
logged and exposed; in-memory responses remain exportable until backend exit.

Legacy notebook batches can be inspected without an LLM call. Their missing
template/configuration provenance is labelled unavailable, not reconstructed from
today's files. Invalid result files are listed as explicit issues. Diagnostics
match the notebook: active-factor Q mapping, missing abstentions, active-only
running means, cumulative coverage, and sample standard deviation (`ddof=1`,
unavailable for fewer than two active values). No convergence pass/fail threshold
is inferred.

Focused tests use temporary directories and stub clients, with no real API calls:

```powershell
python -m unittest tests.test_convergence tests.test_factor_view_orchestrator tests.test_prompts tests.test_aisuite_llm_client tests.test_api -v
```

`tests/test_api.py` exercises all health, evidence, mutation-profile and variant
routes, including listing, retrieval and updates. `tests/test_convergence.py`
exercises all convergence routes, including run history, stopping an in-flight
batch, and finite HTTP SSE streams for external edits and read-error recovery.
Streaming tests mock disconnect timing so no server or indefinite stream is
required. Endpoint coverage includes success paths and selected validation,
not-found and revision/concurrency conflict responses; it is not exhaustive
branch coverage.
