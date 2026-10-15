# Factor View Prompts

`system_prompt.txt` contains the system-message template. Render it with `render_factor_view_system_prompt()` from `app.services.factor_view_prompts`.

`user_prompt.txt` contains the user-message template and evidence snapshot. Render it with `render_factor_view_user_prompt()` from the same module.

Both templates accept the runtime horizon, return convention, optional q bounds, factor definitions, and metric definitions. The user template additionally accepts the evidence snapshot. The output schema and example are in `../fixtures/factor_view_output_contract.json`.

Default runtime values for prompt construction are in `../fixtures/factor_view_defaults.json`. An orchestrator can load these values and override them for a particular request before rendering either prompt.
