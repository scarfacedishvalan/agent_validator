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

Run the backend tests from this directory:

```powershell
py -m unittest discover -s tests -v
```
