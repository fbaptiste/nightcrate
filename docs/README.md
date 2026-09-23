# Documentation

Start with [README.md](../README.md) for features and setup
and [PLAN.md](../PLAN.md) for active work.

## Code map

| Path | Responsibility |
|---|---|
| [backend/src/nightcrate/main.py](../backend/src/nightcrate/main.py) | Startup, router registration, maintenance |
| [api/](../backend/src/nightcrate/api/) | HTTP, DB access, transactions, orchestration |
| [services/](../backend/src/nightcrate/services/) | Astronomy, imaging, parsing, scoring, ingest and session derivation |
| [db/](../backend/src/nightcrate/db/) | Connections and ordered SQL migrations |
| [seed_loader/](../backend/src/nightcrate/seed_loader/), [catalog_loader/](../backend/src/nightcrate/catalog_loader/) | Equipment seeds and external DSO catalogs |
| [data/](../backend/src/nightcrate/data/) | Equipment CSVs and NightCrate editorial catalog data |
| [backend/tests/](../backend/tests/) | Backend regression and integration tests |
| [frontend/src/pages/](../frontend/src/pages/), [components/](../frontend/src/components/) | Routed screens and reusable views |
| [api/](../frontend/src/api/), [stores/](../frontend/src/stores/), [lib/](../frontend/src/lib/), [theme/](../frontend/src/theme/) | Typed clients, state, helpers, theme |

## Maintained references

- [Development decisions](development-decisions.md): feature constraints and known traps.
- [Agent collaboration](agent-collaboration.md): Claude–Codex roles, gates,
  Codex profiles, and review records.
- [Schema diagrams](../DB_SCHEMA.md), [complete DDL](../DB_SCHEMA_DDL.sql),
  [equipment seed reference](../LLM_DB_SPECS.md).
- [DSO catalog architecture](dso-catalog-architecture.md).
- [Target planner](target-planner.md), [scoring](planner-scoring.md),
  [annual-hours algorithm](planner-annual-hours-algorithm.md).
- [Weather algorithms](weather-algorithms.md) and the newer
  [imaging-quality model](imaging-quality-model.md). The latter supersedes older
  composite-score descriptions; forecast redesign is deferred.

## Historical material

- [Plan through v0.41.5](archive/plan-through-v0.41.5.md): original release history,
  proposed future designs and library evaluations.
- `superpowers/specs/` and `superpowers/plans/`: dated design/implementation plans.
- `seed-audit-handoff.md` and `superpowers/seed-data-*.md`: previous seed-work handoffs.
- `../planning_weather/`: prior scoring prototypes and design notes.

These records preserve rationale. They may describe removed features, old schema
shapes or unfinished proposals. Follow current code/migrations and development
decisions when they differ; do not execute an old plan as current instructions.
