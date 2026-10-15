# Backend Architecture Plan

## Scope

Build a standalone FastAPI backend for evidence snapshots and mutation profiles. It will validate and generate reproducible evidence variants for the workbench. No agent execution, experiment runner, backtesting, security-level translation, or portfolio optimization in this phase.

## Proposed Structure

```text
backend/
|-- app/
|   |-- main.py                    FastAPI app, lifespan, local CORS, routers
|   |-- config.py                  Environment settings and SQLite path
|   |-- api/
|   |   `-- routers/
|   |       |-- health.py           Local readiness
|   |       |-- evidence.py         Snapshots and metric catalog
|   |       |-- mutation_profiles.py Profiles and compatibility validation
|   |       `-- variants.py         Preview, generation, retrieval
|   |-- schemas/                   Pydantic API contracts
|   |-- domain/
|   |   `-- mutations.py            Pure validation and deterministic generation
|   |-- services/                  Coordinate domain logic and repositories
|   `-- db/
|       |-- connection.py           SQLite setup and connection lifecycle
|       `-- repositories/           Snapshot, profile, and variant persistence
|-- fixtures/
|   `-- metric_definitions.json     Versioned, read-only metric catalog
|-- data/
|   `-- workbench.sqlite            Local database; exclude from source control
`-- tests/
    |-- test_mutations.py
    `-- test_api.py
```

Routers handle HTTP concerns only. Pydantic schemas mirror the frontend's TypeScript contracts; domain logic owns validation and generation; repositories own SQL. Configure the database path so tests can use a temporary SQLite file.

## Request Flow

```text
React workbench
      |
      | JSON requests / responses
      v
FastAPI router -----> Pydantic schema validation
      |                          |
      v                          v
Application service -----> Mutation domain
      |                          |
      +----------+---------------+
                 |
        +--------+---------+
        |                  |
        v                  v
  SQLite repository   Metric catalog
        |
        v
Persisted snapshots, profiles, variant batches, variants
```

`POST /variants/preview` validates and generates in memory. `POST /variants/generate` persists the same generated evidence and provenance. The backend becomes the reproducibility authority when the UI switches from local generation to HTTP.

## Main API

All routes use the `/api/v1` prefix and camelCase JSON fields to match the frontend.

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | Local readiness |
| GET, POST | `/evidence/snapshots` | List or create immutable snapshots |
| GET | `/evidence/snapshots/{snapshot_id}` | Retrieve one snapshot |
| GET | `/evidence/metrics` | Read the metric-definition catalog |
| GET, POST | `/mutation-profiles` | List or save reusable profiles |
| GET, PUT, DELETE | `/mutation-profiles/{profile_id}` | Retrieve, update, or delete a profile |
| POST | `/mutation-profiles/{profile_id}/validate` | Check profile compatibility against a snapshot |
| POST | `/variants/preview` | Return bounded preview rows and the full variant count; no write |
| POST | `/variants/generate` | Persist a variant batch and its variants |
| GET | `/variants?batch_id=...` | List variants in a batch |
| GET | `/variants/{variant_id}` | Retrieve one generated variant |

Missing or ineligible fields and incompatible profiles return structured validation errors; never silently drop fields. Preview has a row limit but reports the full count. Experiment and run endpoints are deferred until their execution model is designed.

## SQLite Data

| Table | Stored data |
|---|---|
| `evidence_snapshots` | Immutable ID, name, as-of date, numeric JSON values, creation time |
| `mutation_profiles` | Name, field keys, strategy settings, combination mode, timestamps |
| `variant_batches` | Source snapshot, optional profile, exact settings and seed, generator version, count, timestamp |
| `evidence_variants` | Batch ID, generated evidence JSON, changed field keys |

Metric definitions remain in a separate versioned JSON catalog and are read-only in this phase. Use foreign keys from batches to snapshots/profiles and variants to batches. Deleting a profile must not erase variant provenance. Do not create experiment/run tables yet.

## Delivery Order

1. Add backend package, configuration, local CORS, SQLite initialization, and health route.
2. Define Pydantic schemas from `src/features/evidence/` and `src/features/mutations/` contracts.
3. Port generation and validation into pure, tested domain functions, including seeded randomness and both combination modes.
4. Add snapshot/profile repositories and CRUD routes.
5. Add ephemeral preview, persisted generation, provenance, and retrieval routes.
6. Replace frontend local repositories with typed HTTP adapters; keep components independent of API details.

Test deterministic generation, counts, preview limits, invalid inputs, profile compatibility, CRUD, and the distinction between preview (no writes) and generation (persisted). Keep this backend independently runnable and use the sibling `hackathon/backend` only as a convention reference, not a runtime dependency.
