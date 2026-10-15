# Mutation Builder UI

## Scope

A focused workbench for generating and inspecting evidence variants. It is a frontend-only first slice: use local sample data and deterministic generation in the browser, behind an interface that can later call the API. It does not run agents or experiments yet.

## Screen Shape

```text
+--------------------------------------------------------------------------+
| Evidence snapshot: [ Current snapshot v ]                 [Save profile] |
+----------------------------+---------------------------------------------+
| Fields                     | Mutation profile                            |
|                            | Name: [ HML valuation sensitivity        ] |
| [x] HML_valuation_zscore   |                                             |
|     1.6  | numeric         | Strategy: [Explicit] [Range] [Random]       |
| [ ] HML_return_1m          | Values / range / seed controls              |
| [ ] RMW_return_3m          |                                             |
|                            | Apply: [One at a time] [Cartesian]          |
+----------------------------+---------------------------------------------+
| Preview: 4 variants                                      4 total runs   |
| Variant       HML_valuation_zscore   Other changed fields                |
| Baseline      1.6                    -                                   |
| Variant 1     0.5                    -                                   |
| Variant 2     1.0                    -                                   |
| Variant 3     2.0                    -                                   |
+--------------------------------------------------------------------------+
| [Generate variants]       Original snapshot remains unchanged             |
+--------------------------------------------------------------------------+
```

The field list is derived from the selected snapshot and metric metadata, not a fixed factor list. Only numeric, mutation-eligible fields can be selected. Invalid or missing fields are surfaced before preview or save.

## Frontend Boundaries

```text
src/
|-- app/                         App shell, routing, shared layout
|-- features/
|   |-- evidence/                Snapshot selection and field metadata
|   |   |-- components/
|   |   |-- hooks/
|   |   |-- types.ts
|   |   `-- services/             EvidenceRepository interface + local adapter
|   |-- mutations/               Mutation Builder feature
|   |   |-- components/           FieldPicker, StrategyEditor, VariantPreview
|   |   |-- hooks/                Draft/profile/preview state orchestration
|   |   |-- domain/               Pure validation and variant generation
|   |   |-- types.ts              MutationProfile, MutationSpec, Variant
|   |   `-- services/             MutationProfileRepository interface + local adapter
|   `-- experiments/             Future composition of variants into experiments
|-- shared/
|   |-- components/               Reusable controls and tables
|   `-- validation/               Shared form and schema utilities
`-- fixtures/                     Sample snapshots and metric definitions
```

```text
Snapshot + metric definitions
              |
              v
        Field Picker -----> Mutation Draft <----- Strategy Editor
                                  |
                                  v
                        Validate + Preview
                                  |
                    +-------------+-------------+
                    |                           |
                    v                           v
             Save Profile              Generate Variants
          (reusable instructions)     (derived evidence copies)
                    |                           |
                    +----------> Future Experiment Setup
```

## State and Data Ownership

- **Evidence snapshot:** selected, immutable input for generation; never edited by applying a mutation.
- **Mutation draft:** unsaved UI state for selected fields, strategies, combination mode, and seed.
- **Mutation profile:** reusable instructions referencing field keys; persisted separately from evidence and variants.
- **Generated variants:** previewable evidence copies with stable local IDs and provenance to the source snapshot and profile/draft.
- **Experiment:** future feature that consumes variants; it does not own mutation editing or generation logic.

Keep generation and validation as pure domain functions. Components collect inputs and render results; feature hooks coordinate draft state. Repositories own loading/saving, so replacing local fixtures with HTTP calls does not move API details into components.

## First Slice

1. Select a sample evidence snapshot and list eligible numeric fields with their baseline values.
2. Configure one field using explicit values, a range, or seeded random perturbation.
3. Choose one-at-a-time or Cartesian combination when multiple fields are configured.
4. Validate the draft and preview variants plus the resulting count before generation.
5. Generate immutable variants and save/load a named mutation profile locally.

Keep the initial interaction single-screen and preview-first. Add multi-field authoring, profile compatibility checks against other snapshots, and experiment integration through the same feature boundaries when the larger workbench is built.
