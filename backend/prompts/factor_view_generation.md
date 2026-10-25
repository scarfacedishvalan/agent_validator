# Factor View Prompts

`system_prompt.txt` contains the system-message template. Render it with `render_factor_view_system_prompt()` from `app.services.factor_view_prompts`.

`user_prompt.txt` contains the user-message template and evidence snapshot. Render it with `render_factor_view_user_prompt()` from the same module.

Both templates accept the runtime horizon, return convention, optional q bounds, factor definitions, and metric definitions. The user template additionally accepts the evidence snapshot. The output schema and example are in `../fixtures/factor_view_output_contract.json`.

The user renderer accepts `personality_key`, an exact key from `../fixtures/personalities.json`, defaulting to `"Trend-Following Analyst"`. It resolves the selected sentence array to newline-separated instructions and fills `{agent_personality}` with the name and instructions. `load_agent_personality()` can also load these instructions directly. Unknown keys, blank keys, or malformed selected instructions raise an error; they do not fall back to another personality.

The trend-following and contrarian personas use structured, discretionary decisions: identify a prevailing direction, assess corroboration and conflict, decide whether their preferred hypothesis is supported, then estimate magnitude or abstain. Trend-following favors continuation; contrarian requires a defensible reversal rather than substituting a continuation forecast. Both anchor magnitude judgments to relevant evidence without copying historical returns into forecasts, require interpretable metric definitions, and explain the decision in the existing rationale field. These instructions leave judgment over evidence strength and magnitude rather than imposing fixed formulas or thresholds. Improved repeatability must be checked with new repeated-call batches; prompt-rendering tests do not establish behavioral reliability or forecast accuracy.

Default runtime values for prompt construction are in `../fixtures/factor_view_defaults.json`. An orchestrator can load these values and override them for a particular request before rendering either prompt.

`shared_financial_grounding_policy.txt` defines persona-independent principles for interpreting evidence and forming views. The system template includes it through the `{shared_financial_grounding_policy}` placeholder, using the same string-formatting mechanism as the runtime inputs. The renderer loads the file by default; pass `shared_financial_grounding_policy="..."` to `render_factor_view_system_prompt()` to replace it. Blank policies are rejected, and braces within policy text are preserved literally. The policy remains separate from agent-specific behavioral instructions.
