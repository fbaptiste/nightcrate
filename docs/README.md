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
| [services/hips_tiles.py](../backend/src/nightcrate/services/hips_tiles.py) | DSS2 colour HiPS tile planning, source failover, in-memory tile caching and JPEG rendering |
| [services/image_cache.py](../backend/src/nightcrate/services/image_cache.py) | Shared budget, lock, file identity and clearing for the thumbnail and sky-cell caches |
| [services/catalog_progress.py](../backend/src/nightcrate/services/catalog_progress.py) | The single catalog fetch/reload operation and its progress for the Catalogs page |
| [services/dso_sorting.py](../backend/src/nightcrate/services/dso_sorting.py), [services/dso_display.py](../backend/src/nightcrate/services/dso_display.py) | Natural designation order and the label maps used to sort catalog columns |
| [services/gallery.py](../backend/src/nightcrate/services/gallery.py), [api/gallery.py](../backend/src/nightcrate/api/gallery.py) | The gallery: pure filtering, facets, sorting and imaging runs; batched loading and `GET /api/gallery` |
| [services/rig_setups.py](../backend/src/nightcrate/services/rig_setups.py), [api/rig_setups.py](../backend/src/nightcrate/api/rig_setups.py), [api/project_rig_setups.py](../backend/src/nightcrate/api/project_rig_setups.py) | Rig history: part groups, usage and night counts, earlier setups and stamps, corrections, project changes, each project's setups, the night move and equipment usage; the setup-correction and project-setup routes |
| [backend/scripts/make_gallery_workspace.py](../backend/scripts/make_gallery_workspace.py) | Builds a scratch workspace with hundreds of synthetic projects for rendered and speed checks (development only) |
| [core/tasks.py](../backend/src/nightcrate/core/tasks.py) | `settle`: wait for a worker through repeated cancellation before releasing ownership |
| [components/plate-solve/](../frontend/src/components/plate-solve/) | The inline plate-solve panel, its hint model and solve hook, and the overlays |
| [db/](../backend/src/nightcrate/db/) | Connections and ordered yoyo migrations (SQL; Python where SQL cannot express the change, e.g. 0064) |
| [seed_loader/](../backend/src/nightcrate/seed_loader/), [catalog_loader/](../backend/src/nightcrate/catalog_loader/) | Equipment seeds and external DSO catalogs |
| [catalog_loader/catalog_choice.py](../backend/src/nightcrate/catalog_loader/catalog_choice.py), [api/catalog_choice_models.py](../backend/src/nightcrate/api/catalog_choice_models.py) | The app-wide optional-catalog choice (`choice.json`) and its effective state per database; the Admin response models for optional catalogs and removal previews |
| [catalog_loader/designations.py](../backend/src/nightcrate/catalog_loader/designations.py) | The one designation search-key function and canonical MCG, PN G and WR identifiers |
| [catalog_loader/common_names.py](../backend/src/nightcrate/catalog_loader/common_names.py) | Splitting and merging catalog names, and reading NightCrate's reviewed `common_names.csv` |
| [catalog_loader/match_review.py](../backend/src/nightcrate/catalog_loader/match_review.py) | The stated-match screen, run on each new catalog before its first application |
| [wr_loader.py](../backend/src/nightcrate/catalog_loader/wr_loader.py), [hh_loader.py](../backend/src/nightcrate/catalog_loader/hh_loader.py), [hash_loader.py](../backend/src/nightcrate/catalog_loader/hash_loader.py), [lbn_loader.py](../backend/src/nightcrate/catalog_loader/lbn_loader.py), [ldn_loader.py](../backend/src/nightcrate/catalog_loader/ldn_loader.py), [melotte_loader.py](../backend/src/nightcrate/catalog_loader/melotte_loader.py), [aco_loader.py](../backend/src/nightcrate/catalog_loader/aco_loader.py), [mcg_loader.py](../backend/src/nightcrate/catalog_loader/mcg_loader.py), [arp_loader.py](../backend/src/nightcrate/catalog_loader/arp_loader.py) | Pure collectors for the optional catalogs, called by `reconcile.build_object_set` in `COLLECTOR_ORDER` |
| [data/](../backend/src/nightcrate/data/) | Equipment CSVs and NightCrate editorial catalog data |
| [data/catalogs/nightcrate/](../backend/src/nightcrate/data/catalogs/nightcrate/) | Shipped lists (GPL-3.0-or-later): augment, cross-references and external-reference overrides, plus the Melotte list (`melotte.csv`), reviewed Arp members (`arp_members.csv`), "part of" rows (`dso_parts.csv`) and match overrides (`dso_match_overrides.csv`) |
| [backend/tests/](../backend/tests/) | Backend regression and integration tests |
| [frontend/src/pages/](../frontend/src/pages/), [components/](../frontend/src/components/) | Routed screens and reusable views |
| [components/admin/StarCatalogAdminSection.tsx](../frontend/src/components/admin/StarCatalogAdminSection.tsx) | Plate-solving star download and field-range controls |
| [components/gallery/](../frontend/src/components/gallery/), [pages/GalleryPage.tsx](../frontend/src/pages/GalleryPage.tsx), [lib/galleryRendition.ts](../frontend/src/lib/galleryRendition.ts) | The gallery page: filters, grids and list, turning cards, the full-size viewer, and framing or rendition choice and date formatting |
| [components/projects/ThumbnailCropEditor.tsx](../frontend/src/components/projects/ThumbnailCropEditor.tsx), [lib/thumbnailFrame.ts](../frontend/src/lib/thumbnailFrame.ts) | The thumbnail framing editor and its pure 4:3 fit-box geometry |
| [components/common/ViewToggle.tsx](../frontend/src/components/common/ViewToggle.tsx), [components/common/NearViewportImage.tsx](../frontend/src/components/common/NearViewportImage.tsx) | The icon view picker shared by Gallery and Projects, and project images loaded as they near the viewport |
| [components/rigs/RigChangePrompt.tsx](../frontend/src/components/rigs/RigChangePrompt.tsx), [RigPartsForm.tsx](../frontend/src/components/rigs/RigPartsForm.tsx), [EarlierSetupsList.tsx](../frontend/src/components/rigs/EarlierSetupsList.tsx), [CorrectSetupDialog.tsx](../frontend/src/components/rigs/CorrectSetupDialog.tsx) | The "existing projects or from now on" question, the shared parts editor, and a rig's earlier setups |
| [api/project_night_notes.py](../backend/src/nightcrate/api/project_night_notes.py) | Night notes: list, save and delete one note per project night |
| [components/projects/ProjectSessionsTab.tsx](../frontend/src/components/projects/ProjectSessionsTab.tsx), [SessionNightBlock.tsx](../frontend/src/components/projects/SessionNightBlock.tsx), [NightNoteDialog.tsx](../frontend/src/components/projects/NightNoteDialog.tsx), [ProjectNotesTab.tsx](../frontend/src/components/projects/ProjectNotesTab.tsx), [filterColors.ts](../frontend/src/components/projects/filterColors.ts), [FilterSwatch.tsx](../frontend/src/components/projects/FilterSwatch.tsx) | The Sessions tab's night blocks and night notes, the Notes tab, and filter colours, swatches and order |
| [components/projects/ProjectCatalogTab.tsx](../frontend/src/components/projects/ProjectCatalogTab.tsx), [CatalogFrameTable.tsx](../frontend/src/components/projects/CatalogFrameTable.tsx), [CatalogThumbnailSheet.tsx](../frontend/src/components/projects/CatalogThumbnailSheet.tsx), [CatalogMasterTable.tsx](../frontend/src/components/projects/CatalogMasterTable.tsx), [CatalogOtherTable.tsx](../frontend/src/components/projects/CatalogOtherTable.tsx) | The project's Files tab: source folders, the frame table with night headings, the thumbnail sheet, masters and other files |
| [components/projects/ProjectEquipmentSection.tsx](../frontend/src/components/projects/ProjectEquipmentSection.tsx), [ProjectRigSetupPanel.tsx](../frontend/src/components/projects/ProjectRigSetupPanel.tsx), [ProjectRigChangeDialog.tsx](../frontend/src/components/projects/ProjectRigChangeDialog.tsx), [ProjectSoftwareField.tsx](../frontend/src/components/projects/ProjectSoftwareField.tsx), [PlateSolveLine.tsx](../frontend/src/components/projects/PlateSolveLine.tsx) | The project Overview's Equipment section (one row per rig) and the setup panel under it, a project's own rig changes, its software with versions, and the plate-solve line under the main targets |
| [components/equipment/SoftwareVersionsField.tsx](../frontend/src/components/equipment/SoftwareVersionsField.tsx), [shared/EquipmentUsageNote.tsx](../frontend/src/components/equipment/shared/EquipmentUsageNote.tsx), [components/shared/softwareOrder.ts](../frontend/src/components/shared/softwareOrder.ts) | Program versions, the "Used by N rigs and M projects" note, and the software picker order |
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
