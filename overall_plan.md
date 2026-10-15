Build an Agent Experiment Workbench for Quantitative Factor Views
1. Project Context
I am developing an agentic quantitative investment framework that generates factor-level investment views for a Black–Litterman portfolio optimization model.

The immediate goal is to build a standalone experimentation tool that helps me iteratively develop and evaluate LLM prompts, models, and agent configurations before integrating them into a historical backtesting framework.

The current experiment focuses exclusively on factor-level investment views. The agent receives a snapshot of factor-related evidence, decides which factors warrant views, and estimates the expected return (q) for each selected factor. Asset exposures and the translation of factor views into security-level views are outside the scope of this initial tool.

The tool should be flexible enough to support future extensions without requiring a major redesign.

2. Technology Direction
Use the following as the initial technology direction:

Frontend: React with TypeScript.
Backend: Python with FastAPI.
Persistence: A lightweight local database such as SQLite is sufficient initially.
Data processing: Python, with pandas and NumPy where useful.
LLM integration: Keep the model interface modular so different models and providers can be compared. LangChain or LangGraph may be introduced if they provide a concrete benefit, but the experiment runner should not depend unnecessarily on a particular agent framework.
You may recommend alternatives where there is a compelling reason. Prioritize a maintainable, locally runnable development environment.

3. Core Workflow
The primary workflow should be:

Load or create an evidence snapshot.
Edit the evidence and its metric definitions.
Configure the agent’s prompts and model parameters.
Optionally define mutations to generate multiple evidence variants.
Configure an experiment that varies one or more dimensions.
Execute the experiment and inspect the resulting runs.
Compare results, identify behavioral differences, and save useful configurations for reuse.
The UI should function as an experiment workbench rather than a conversational chatbot.

4. Evidence Management
Evidence is supplied to the agent as JSON. For the initial implementation, prefer a flat JSON object with numeric fields, for example:

{
“HML_return_1m”: -0.032,
“HML_return_3m”: -0.071,
“HML_return_12m”: -0.045,
“HML_valuation_zscore”: 1.6,
“RMW_return_3m”: 0.042,
“RMW_return_12m”: 0.083,
“MOM_return_1m”: -0.025,
“MOM_return_12m”: 0.124,
“treasury_yield_10y”: 0.042
}

These are illustrative values, not actual market data.

The evidence editor should allow me to:

Create, load, edit, and save evidence snapshots.
Add and remove fields without requiring frontend code changes.
Edit raw JSON, with useful validation and error messages.
Inspect evidence in a more structured form where practical.
Identify numeric fields that could be selected for mutation.
Preserve the original snapshot when generating variants.
Do not rigidly hard-code the available factors or evidence fields into the UI.

Metric definitions and metadata should be maintained separately from the evidence values. They should be capable of documenting descriptions, units, return horizons, sign conventions, and reasonable validation constraints. Avoid treating every numeric field as a valid mutation target automatically; let the user select the fields to vary.

5. Mutation Profiles and Test Data Generation
A major requirement is generating test evidence interactively through the UI, without manually editing JSON for every experiment.

I want to select a numeric evidence field and configure how it should vary. Useful mutation strategies include:

Explicit values, such as testing a valuation z-score at 0.5, 1.0, 1.6, and 2.0.
Numeric ranges with configurable start, end, and step.
Random perturbations around a baseline, with reproducible random seeds.
Combinations of mutations across multiple fields.
Support at least one-at-a-time variations and consider Cartesian combinations. The UI should preview the generated variants and indicate the number of runs that would result before execution.

Mutation definitions should be saved as named, reusable profiles, separate from both the original evidence and the generated variants.

For example, a profile named hml_valuation_sensitivity might vary only the HML valuation z-score. The same profile should be reusable against another compatible evidence snapshot.

The design should distinguish between:

Evidence snapshots: the actual input data.
Mutation profiles: instructions describing how to generate variations.
Generated variants: concrete evidence inputs created by applying a profile.
Experiments: the configurations and runs used to evaluate agent behavior.
If a base snapshot changes and a saved profile references missing or incompatible fields, report the problem rather than silently ignoring it.

6. Prompt and Model Configuration
I want to be able to modify and compare all significant parts of the agent configuration through the UI.

Prompts should be composed from independently editable components where appropriate, such as:

Shared investment reasonableness and evidence-discipline policy.
Agent-specific persona or investment mandate.
Task instructions for selecting factors and generating expected returns.
Output-format instructions.
The shared policy should discourage unsupported, economically implausible, or excessively extreme views. It should require evidence-based rationales, consideration of contradictory signals, correct units, and abstention when evidence is insufficient.

The aggressive and conservative personas should differ in their tolerance for uncertainty, willingness to express contrarian views, and interpretation of conflicting evidence. Both should follow the same shared policy and deterministic validation rules.

Model configuration should support relevant parameters exposed by the selected provider, such as model identifier, temperature, token limits, and structured-output capabilities.

Avoid tying the UI to one specific prompt template, model, provider, or fixed set of parameters.

For reproducibility, preserve the exact prompt components and model configuration used for each run, even when the currently saved configuration is edited later.

7. Experiment Design
The tool should support several experiment types:

Repeatability testing: Run the same evidence, prompts, and model configuration multiple times to observe variability.

Prompt comparison: Compare different prompt versions while holding evidence and model settings constant.

Model comparison: Compare models or model parameters using otherwise identical inputs.

Evidence sensitivity: Vary one evidence field at a time and observe changes in factor selection and (q).

Multi-dimensional experiments: Combine multiple varying dimensions when needed, with a preview of the resulting experiment size.

The user should be able to specify a baseline configuration, select which dimensions to vary, and choose the number of repetitions where applicable.

Make it easy to hold all but one dimension constant. This is important for identifying why an agent’s output changes.

The execution layer should be separate from HTTP request handling so experiments involving many model calls do not block the API. Include basic execution status, error reporting, and the ability to retrieve completed and failed runs.

8. Results and Analysis
For every run, retain enough information to reproduce and diagnose its output.

Useful run information includes:

Evidence snapshot and generated variant identifiers.
Exact prompt versions and rendered prompt.
Model identifier and parameters.
Raw model response and parsed output.
Selected factors and expected-return estimates (q).
Confidence scores and abstentions, if supplied by the agent.
Evidence references and rationales.
Validation results and error messages.
Execution status, latency, and token usage where available.
The UI should provide:

A table of runs with filtering and sorting.
Side-by-side comparison of selected factors and (q).
Visibility into which factors were selected or omitted.
Charts showing how (q) changes across evidence values or configurations.
Inspection of the full prompt, input evidence, raw response, and parsed output for any run.
Export of results for further analysis in Python or a spreadsheet.
Useful derived metrics include factor-selection frequency, abstention frequency, variability in (q) across repeated runs, sensitivity to individual evidence fields, and output-validation failure rates.

Do not assume that a model’s self-reported confidence is statistically calibrated.

9. Validation and Reproducibility
LLM instructions alone should not be relied upon to prevent invalid outputs.

Implement a deterministic validation layer for concerns such as:

Valid JSON and expected output structure.
Permitted factor names, where configured.
Evidence references that actually exist.
Correct direction and sign consistency for (q).
Correct return units and annualization conventions.
Configurable bounds on expected-return magnitudes.
Missing, malformed, or incompatible evidence fields.
Numerical bounds should be configurable rather than buried in prompt text.

Preserve the exact evidence, prompts, model parameters, mutation settings, random seeds, and validation configuration used by each run. Store raw responses alongside parsed outputs.

Where supported, record provider request identifiers and model version information. Recognize that recording a configuration does not guarantee deterministic model output.

10. Scope and Implementation Approach
Build this as an initial local development tool, not a production platform.

Prioritize a working end-to-end workflow over elaborate UI design. I should be able to edit evidence, configure a prompt and model, generate variants, run an experiment, and inspect the results without manually manipulating files or database records.

Keep the evidence schema flexible and avoid unnecessary abstractions. At the same time, separate evidence, prompts, model configuration, mutation profiles, experiments, and individual runs sufficiently to make future extension straightforward.

Do not implement historical backtesting, security-level view translation, asset exposure processing, or portfolio optimization in this phase.

Before making major architectural decisions, inspect the existing repository and explain any assumptions. If a project structure or implementation already exists, extend it rather than replacing it unnecessarily.

Start by proposing a concise implementation plan and identifying the key design decisions that need to be made. Then implement the smallest useful end-to-end version, with clear instructions for running the frontend and backend locally.