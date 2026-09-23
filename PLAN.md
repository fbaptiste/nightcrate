# NightCrate — active plan

**Version:** v0.41.6 — General cleanup

**Branch:** `v0.41.6/general-cleanup`

**Status:** Complete — awaiting merge

## v0.41.6 — General cleanup

Tighten documentation and development workflows while preserving current design
and coding decisions. Finalization and PR publication are authorized; merging
remains with Fred. Forecast redesign is deferred.

- [x] Start from updated `main` on the cleanup branch.
- [x] Condense shared instructions and retain feature constraints in a linked reference.
- [x] Consolidate useful snapshot details into README, the code map and active roadmap.
- [x] Remove the retired brief, current-state snapshot, snapshot prompt and primitive inventory.
- [x] Keep the active roadmap short; archive release history and superseded designs.
- [x] Simplify project skills, remove stale agent/tool assumptions, and preserve authorization boundaries.
- [x] Support optional, untracked local agent instructions without publishing private configuration.
- [x] Verify documentation links, retained constraints, and staged changes.
- [x] Synchronize release version files and reference headers to 0.41.6.
- [x] Complete release checks and review the release diff.

Verified by Codex: backend Ruff lint and formatting (238 files); full pytest suite
(2,549 passed, 3 skipped); frontend TypeScript/production build; 148 local links;
skill structure, version consistency, and diff/privacy checks. Acknowledgment
tables and historical plan content are preserved, with archive link repairs.

Bandit found zero medium/high and three existing low-severity findings, deferred
with Fred's approval below. The frontend build reports its existing bundle-size
warning; pytest reports 28 warnings. Application behavior, schema, and dependency
versions are unchanged.

## Roadmap

These are planned capabilities, not implemented behavior. Current functionality
is in [README.md](README.md#features); coding constraints
are in [development decisions](docs/development-decisions.md).

### v0.42.0 — Calibration coverage and gallery promotion

- Show per-light dark/flat/bias coverage from the existing `calibration_coverage`
  view. Matching remains per project and rig; there is no shared calibration
  library. Binding an existing calibration folder to a project is supported.
- Guard manual/derived session overlap so the same captures do not silently
  inflate integration. Decide warning versus reconciliation before implementing;
  the old proposed `COALESCE(manual, derived)` model is not current behavior.
  Derived rows can also become stale after catalog changes; refreshing them
  currently requires an explicit derive request.
- Promote cataloged subs or processed images into the project gallery.
- Verify against real calibration data and gallery output. Integration describes
  cataloged capture time; it does not imply which subs survived processing.

### v0.43.0 — Guiding association and session timeline

Guiding storage tables exist; the app does not yet populate them.

- Reuse the PHD2 parser to populate `guiding_log_file`, `guiding_sample`, and
  `dither_event`. Associate logs with the correct rig/night session; guide
  equipment comes from its declared rig.
- Derive per-sub RMS, peaks, and sample counts from the exposure's time interval;
  do not store redundant per-sub guiding aggregates.
- Embed the PHD2 analyzer as a project overlay, following the image-analyzer
  pattern. Opening from a sub/timeline scopes the view to that time range.
- Build a vertical, time-proportional timeline: time axis, continuous RA/Dec
  strip, dither markers, and exposure blocks with thumbnails/filter/HFR.
  Fold long idle gaps (about 10 minutes or more); decimate guiding data server-side.
- Reuse data/metrics and the embedded analyzer, not a rotated copy of the PHD2
  chart. Clicking a sub opens the image analyzer; clicking guiding opens PHD2.
- Include twilight, target altitude, moon altitude/separation, illumination,
  moonrise/set, and transit from the existing astronomy services.
- Verify alignment on a real night, including multiple rigs and gap folding.

### v0.44.0 — Capture logs and timeline context

Session-log, event and autofocus tables exist; the app does not yet populate them.

- Research/parse ASIAIR Autorun and N.I.N.A. session logs into `session_event`;
  parse N.I.N.A. autofocus JSON into `autofocus_run`.
- Add autofocus, meridian flips, filter changes, solve failures, errors/warnings,
  and header-derived gain/offset/binning changes to the timeline.
- Add optional historical conditions, frame HFR/star-count/background trends,
  sensor temperature versus set point, dew spread, and guiding SNR/star-mass bands.
- Provide a shared time readout and strip toggles. Guiding, subs, sky context,
  and events default on; trends, thermal and conditions are optional.

### Later: mosaics

- Support panel identity, framing, solves and integration rollups, with a layout
  view and multi-panel FOV preview. Preserve current multiple-main-target support.
- Settle schema/uniqueness at implementation time; old panel-0 proposals and
  integration goals predate the current schema and are not migration instructions.
- Automatic panel detection from capture headers/plans remains a separate proposal.

## Deferred — known work not yet versioned

### Weather

Discuss separately after general cleanup. The prior proposals for configurable
quality terms, precipitation tolerance, rig-aware wind limits, score validation,
and unrendered model details remain in the
[historical weather plan](docs/archive/plan-through-v0.41.5.md#v0416--configurable-score--rig-aware-gates).
Existing formulas and their evidence remain in [the model rationale](docs/imaging-quality-model.md).
This release changes no weather behavior or scoring decisions.

### Frame quality and consolidation

- Reuse stored catalog measurements in the embedded analyzer; share/cache the
  overlapping image-quality and aberration detection work.
- Consider median subsampling only with pinned measurements and deliberate stored
  metric invalidation. Evaluate larger analysis batches against cancel latency.
- Virtualize long catalog lists if needed; keep sorting/filtering server-side.
- Frontend routes currently load without code splitting; no frontend test script
  is configured. Revisit these gaps as UI work warrants.
- Consolidate the three pixel-format dispatch paths with a resolved-source loader.
- Replace `path_resolver`'s FastAPI exception with a domain exception translated
  by routers; remove the dependent string-name exception checks.

### Project workflow

- Cross-project object/filter/date search; planner "already imaged" indicators.
- Create a project from a planner target; richer home dashboard and equipment
  usage totals from catalog data.
- Track processed-image provenance (subs → stack → final).
- Slideshows, collections, curated observing lists, and export/sharing integrations.
- Catalog file verification and a database backup/export interface.
- Optional file copy/reorganization; cataloging in place remains the default.
- Native distribution (Tauri) and broader smart-scope ingest after the core workflow.

### Analysis tools

- Aberration heatmaps/vector fields, comparisons across frames/filters/nights,
  user zones/notes, and image/CSV exports.
- Any automatic optical diagnosis needs validation; historical angle/eccentricity
  thresholds are proposals, not established diagnostic rules.
- Background-region statistics and quality indicators while browsing frames.
- Equipment/manufacturer links for specifications, manuals, drivers, and forums.

### Security follow-up

- Review three existing low-severity Bandit findings in
  [plate_solve.py](backend/src/nightcrate/services/plate_solve.py): B101 on the
  subprocess stream assertions (lines 679 and 690), and B110 on the optional
  image-dimension fallback (line 789). The v0.41.6 scan found no medium/high
  findings. Fred approved deferring these to the later code review; keep them
  visible rather than adding suppressions for this documentation release.

## Settled scope

Current implementation constraints are maintained in
[development decisions](docs/development-decisions.md#projects-catalog-and-sessions).
In particular: header-driven classification, project-owned file identity, declared
rigs/targets, immediate project saves, on-demand session derivation, project-local
calibration matching, and no processing accept/reject workflow.

Automatic FITS equipment inference, alias review queues, per-filter integration
goals, and the PHD2 spectrum/unguided-RA features were removed. Historical plans
must not be used to reintroduce them. Speculative AI integrations are outside the
active roadmap; their old proposals remain only in the archive.

## History and references

[The plan through v0.41.5](docs/archive/plan-through-v0.41.5.md) preserves release
history, original design proposals, and library evaluations. Consult it for
rationale, not present-day status or executable migration definitions.

- [Schema diagrams](DB_SCHEMA.md) and [DDL](DB_SCHEMA_DDL.sql)
- [Equipment seed reference](LLM_DB_SPECS.md)
- [Planner scoring](docs/planner-scoring.md) and [annual visibility](docs/planner-annual-hours-algorithm.md)
- [DSO catalog architecture](docs/dso-catalog-architecture.md)

Dependency policy is in `CLAUDE.md`; installed dependencies and acknowledgments
are in `README.md`. Recheck a candidate's license at adoption time.
