# Documentation

Start with [README.md](../README.md) for features and setup
and [PLAN.md](../PLAN.md) for active work.

## Code map

| Path | Responsibility |
|---|---|
| [backend/src/nightcrate/main.py](../backend/src/nightcrate/main.py) | Startup, router registration, maintenance |
| [api/](../backend/src/nightcrate/api/) | HTTP, DB access, transactions, orchestration |
| [services/](../backend/src/nightcrate/services/) | Astronomy, imaging, parsing, scoring, ingest and session derivation |
| [services/star_catalog/](../backend/src/nightcrate/services/star_catalog/) | Siril Gaia DR3 catalog installation, field-range indexes and mapped handles |
| [services/native_solver/](../backend/src/nightcrate/services/native_solver/) | Built-in extraction, geometric index search and WCS verification |
| [api/star_catalog.py](../backend/src/nightcrate/api/star_catalog.py) | Plate-solving star-data administration routes |
| [services/plate_solve.py](../backend/src/nightcrate/services/plate_solve.py), [services/solve_operations.py](../backend/src/nightcrate/services/solve_operations.py) | Solver dispatch, the ASTAP step chain, and solve identity, cancellation and progress |
| [services/image_preview.py](../backend/src/nightcrate/services/image_preview.py) | Cached JPEG previews of any supported image path |
| [components/plate-solve/](../frontend/src/components/plate-solve/) | The inline plate-solve panel, its hint model and solve hook, and the overlays |
| [db/](../backend/src/nightcrate/db/) | Connections and ordered yoyo migrations (SQL; Python where SQL cannot express the change, e.g. 0064) |
| [seed_loader/](../backend/src/nightcrate/seed_loader/), [catalog_loader/](../backend/src/nightcrate/catalog_loader/) | Equipment seeds and external DSO catalogs |
| [data/](../backend/src/nightcrate/data/) | Equipment CSVs and NightCrate editorial catalog data |
| [backend/tests/](../backend/tests/) | Backend regression and integration tests |
| [frontend/src/pages/](../frontend/src/pages/), [components/](../frontend/src/components/) | Routed screens and reusable views |
| [components/admin/StarCatalogAdminSection.tsx](../frontend/src/components/admin/StarCatalogAdminSection.tsx) | Plate-solving star download and field-range controls |
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
- [Weather algorithms](weather-algorithms.md): the personal imaging verdict
  (v0.41.9). The retired 0–100 score is archived in
  [imaging-quality model](archive/imaging-quality-model.md).

## Historical material

- [Plan through v0.41.5](archive/plan-through-v0.41.5.md): original release history,
  proposed future designs and library evaluations.
- `superpowers/specs/` and `superpowers/plans/`: dated design/implementation plans.
- `seed-audit-handoff.md` and `superpowers/seed-data-*.md`: previous seed-work handoffs.
- `../planning_weather/`: prior scoring prototypes and design notes.

These records preserve rationale. They may describe removed features, old schema
shapes or unfinished proposals. Follow current code/migrations and development
decisions when they differ; do not execute an old plan as current instructions.
