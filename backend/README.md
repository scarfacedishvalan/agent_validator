# Agent Experiment Workbench API

Run from this directory on Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

The API listens at `http://127.0.0.1:8000`; interactive OpenAPI docs are at `/docs`. The React workbench connects to this local API by default. On first use it creates the illustrative sample evidence snapshot if the database is empty.

SQLite is created at `backend/data/workbench.sqlite` by default. Set `AGENT_VALIDATOR_DB_PATH` to use another local path. The metric catalog is loaded from `backend/fixtures/metric_definitions.json` and is read-only in this phase.

Factor definitions are kept separately in `backend/fixtures/factor_definitions.json`. The output schema and example live in `backend/fixtures/factor_view_output_contract.json` and can be loaded with `app.services.factor_view_prompts.load_factor_view_output_contract()`. The system prompt is `backend/prompts/factor_view_generation.md`; it is not yet connected to an LLM endpoint.

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

Open `../factor_view_convergence.ipynb` from the repository root to compare repeated calls on identical evidence. Install `../notebook-requirements.txt` into the selected notebook kernel if needed. The notebook defaults to 10 calls and the trend-following personality; configure the call count, personality key, model, and snapshot before running the live-call cell. Set `OPENAI_API_KEY` securely in the kernel environment.

The plots show individual Q estimates, active-only running means and distributions, and cumulative active-view fractions for every catalog factor. Abstentions remain missing, never zero; full responses remain available for inspecting rationales. Live calls incur API costs, and errors stop the batch without silently skipping or retrying failures. These diagnostics assess repeatability, not forecast accuracy or proof of convergence.

Each batch saves a single uniquely named JSON under `convergence_results/` (excluded from Git). It includes every full response and the experiment inputs, with an atomic checkpoint after each successful iteration. Check `complete` and the requested/completed iteration counts before treating a saved batch as finished. Configure `OUTPUT_DIR` in the notebook or pass `output_path` to `collect_runs()`; an existing output file is rejected rather than overwritten.
