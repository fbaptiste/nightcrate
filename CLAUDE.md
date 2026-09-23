# NightCrate — project instructions

Applies to every agent. `AGENTS.md` points here; keep one source of instructions.
Project skills live in `.claude/skills/`; edit those files, not the pointers in
`.agents/skills/`. Use the running agent's identity and memory location.

Also read `CLAUDE.local.md` at the repository root if present and not already
loaded. It holds optional machine-specific guidance and must remain untracked.

## Product and scope

NightCrate is a free, MIT-licensed application for astrophotographers to plan,
catalog, and understand their imaging work. It runs locally on Mac, Windows,
and Linux, between capture software (N.I.N.A./ASIAIR) and processing software
(PixInsight/Siril). Files are cataloged in place by default.

- Prioritize connections between projects, exposures, equipment, guiding, and
  conditions. New features should support a concrete imaging decision.
- Catalog and correlate. Sub-frame rejection, weighting, and processing belong
  in processing software; the catalog's rejection fields are dormant.
- Account for multiple rigs, multi-night projects, partial captures, archives,
  offline volumes, polar twilight, and southern-hemisphere seasons.
- Keep units explicit, missing values missing, and facts separate from estimates.
  Verify external schemas, catalog identifiers, and scientific formulas.
- Keep the data model normalized. Add typed fields and relationships where
  appropriate; raw source payloads are retained for re-parsing, not as a substitute
  for modeled data. Speculative AI features do not determine current scope.
- Explain meaningful tradeoffs and challenge unnecessary complexity. Ask one
  decision at a time, with a recommendation and reason. Execute routine choices
  within the user's authorization.

## Documentation map

| File | Purpose |
|---|---|
| [README.md](README.md) | User overview, setup, acknowledgments |
| [PLAN.md](PLAN.md) | Current release and remaining work |
| [docs/README.md](docs/README.md) | Code map and documentation index |
| [docs/development-decisions.md](docs/development-decisions.md) | Feature-specific constraints and regression traps |
| [DB_SCHEMA.md](DB_SCHEMA.md), [DB_SCHEMA_DDL.sql](DB_SCHEMA_DDL.sql) | Schema diagrams and complete DDL |
| [LLM_DB_SPECS.md](LLM_DB_SPECS.md) | Equipment seed-data authoring reference |
| [NightCrate_Equipment_and_Technical_Context.md](NightCrate_Equipment_and_Technical_Context.md) | Reference capture formats and equipment context |

**Before changing a feature, read its section in `docs/development-decisions.md`.**
Use code and migrations to resolve stale documentation. Update current summaries
in place; keep release narratives in `docs/archive/`. Historical specs are not
instructions to restore removed features.

## Architecture

- **Backend:** Python 3.14, FastAPI, Pydantic. `uv` manages dependencies and runs
  commands (`uv add`, `uv sync`, `uv run`). SQLite uses raw SQL through
  `aiosqlite`; migrations use yoyo. No ORM.
- **Frontend:** React/TypeScript/Vite, MUI, Zustand, TanStack Query. D3 for complex
  charts; MUI X Community for simpler charts and controls. No MUI X Pro/Premium.
  Use MUI's `sx`/`styled`; do not add Tailwind, shadcn, `tailwind-merge`,
  `class-variance-authority`, `clsx`, `lucide-react`, or `@base-ui/react`.
- **Boundaries:** `api/` owns HTTP, transactions, and orchestration. Services must
  not import `api/` or FastAPI. Prefer pure services with adjacent Pydantic models;
  existing ingest/derivation helpers take a caller-owned DB connection and never
  commit. Existing `path_resolver` HTTP exceptions are a known boundary violation,
  not a pattern to copy.
- **Runtime:** local browser app; no native wrapper yet. Use `platformdirs` for
  app data, user-selected workspaces for databases/project images, and portable
  path handling. Tauri is the deferred wrapper option; Electron was rejected for
  its bundled-browser footprint.
- **Work:** request-driven; no recurring scheduler. CPU-heavy ingest/analysis uses
  per-run process pools. Close pools in `finally` or a context manager; persistent
  pools leave workers alive and wedge `uvicorn --reload`.
- **GPU:** optional mlx (Apple Silicon) or CuPy (CUDA), numpy fallback. Use
  `core/compute.py`; capability probes catch unusable installations as well as
  missing imports. Never invoke the GPU backend from concurrent worker threads.
  Catalog thumbnails and frame-quality workers must remain numpy-only.
- Keep mlx's dependency marker `sys_platform == 'darwin' and
  platform_machine == 'arm64'`: it has no Intel wheel or source distribution.
  Changes require both native resolution and
  `uv sync --python-platform x86_64-apple-darwin --dry-run` (mlx absent on Intel).

## Shared patterns

- Settings are `settings(key, value_json, updated_at)`, one Pydantic field per row.
  Add defaults to `core/config.py:Settings`; no migration is needed. Computed
  values such as the detected GPU name must not become persisted settings.
  Invalid stored JSON is ignored and validation failures fall back to defaults.
  GPU acceleration and maximum worker cores are runtime preferences; a NULL
  core limit defaults to CPU count minus one.
- Outbound HTTP uses `services/http_client.py:get`: 30 s timeout, one retry after
  500 ms for transient failures. Translate failures at the HTTP boundary.
- Use structured log prefixes. Router 500 handlers must log tracebacks with
  `logger.exception`. `NIGHTCRATE_LOG_LEVEL` defaults to INFO.
- Reuse `api/_common.py` helpers and the equipment router factories for CRUD.
- Resolve plain, archive, and PixInsight virtual paths through `path_resolver`.
  New path-to-pixel callers use `pixel_loader`; it raises domain errors and is
  worker-safe. Two older resolved-source dispatchers remain to be consolidated.
- Disk caches that outlive a database use stable content/sky identities, never
  database IDs. Rehydrate their index before sweeping orphans.
- All frontend API calls are same-origin. LAN mode proxies through Vite; never
  hardcode a backend origin into frontend requests.

## Database and data preservation

- **Never edit an existing migration, even one added on this unmerged branch.**
  Development reloads apply migrations immediately; yoyo will not rerun an
  edited file. Add the next numbered forward migration instead.
- Verify upgrades on a copy of a database at the preceding migration, as well as
  a fresh database. Preserve user records; check integrity and foreign keys.
- Equipment vocabularies use closed CHECK constraints. Vocabulary changes need
  a migration and matching loader/model changes.
- Seed changes must preserve user edits. Field renames require compatible hash
  rehashing; see the seed-loader decisions before changing seeded columns.

## UI

- Colorblind-safe blue/orange/teal or viridis; use text, shape, or pattern where
  color alone would carry meaning. Avoid red/green and purple/amber pairings.
- Use theme tokens, including `common.white`/`common.black`. Any required hex
  color must have six digits; alpha suffixes break on three-digit hex.
- No question-mark help icons or tooltip underlines.
- JSX Unicode escapes need expressions, not quoted attributes. Use actual
  Unicode or `{"≈"}` where React does not recognize a named HTML entity.
- MUI Typography variants override inherited font sizing. Explicitly inherit
  `fontSize`/`lineHeight` when container sizing depends on them.
- Preserve native form-control `colorScheme`, tablet gesture handling, and
  accessible chart interactions; see the image/tablet decisions.

## Development and verification

From the root: `make install`, `make dev`, `make backend`, `make frontend`,
`make test`, or `make test-fast`. `make dev-lan` enables tablet access on a trusted
LAN; both servers bind to the network and the backend is unauthenticated.
Normal `make dev` binds the backend to localhost.

Before committing, run the applicable checks:

```bash
# backend/
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run bandit -r src/
uv run pytest

# frontend/
npm run build
```

New behavior needs tests for normal, edge, and failure cases. Assert concrete
values; scoring changes need hand-computed regression examples. Verify downstream
behavior before removing guards. Periodically run
`uv run coverage report --include="src/nightcrate/*"` and prevent module coverage
regressions. Python 3.14 permits unparenthesized multiple exceptions; ruff removing
their parentheses is valid syntax.

Documentation changes need diff, link, and factual checks. Run the full release
checklist at finalization; report exactly what was verified during each task.

**Keep changes staged and uncommitted until Fred explicitly authorizes a commit.**
Opening a later PR does not authorize committing now. Follow `start-version`,
`sync-docs`, and `finalize-session` for their respective workflows. Never force-push.

## Public repository

Everything committed is public and persists in history. Do not add secrets,
precise personal locations, private network details, contact/identity information,
business/financial details, or personal hardware/health information. Use generic
examples. The existing public civic test location (`33.4484, -112.0740`,
`America/Phoenix`) is intentional; do not substitute home coordinates.

Keep `.env`, certificates, databases, and other ignored local data untracked.
Scan staged changes before committing. Flag sensitive data already present before
publishing; do not rewrite history without an explicit decision.

## Dependencies and licenses

Review licenses before adding dependencies; record additions and required credits
in README's acknowledgments. Check data-source terms separately from library terms.

- Permissive MIT/BSD/Apache/ISC/HPND/PSF/CC0/Unlicense/0BSD are acceptable. SIL OFL
  fonts are acceptable; BSD-4-Clause needs its advertising attribution. MPL-2.0
  requires preserving obligations on modified MPL files.
- LGPL Python runtime imports are permitted (e.g. sep, py7zr). Discuss modified
  library source, static linking, or redistribution/bundling before proceeding;
  carry the applicable source and license obligations into packaging.
- Do not add GPL/AGPL or non-open-source SSPL, BUSL, Commons Clause, Elastic,
  Confluent, or Redis Source Available dependencies. For dual licensing, select
  the compatible license explicitly.
- External programs such as ASTAP may be called across a process boundary.
  Bundling them needs a separate distribution/license review.
- Only MUI X Community features. Keep the clean-room XISF reader. Prefer
  `opencv-python-headless`; `opencv-contrib-python` needs case-by-case review.
  Do not use rawpy/LibRaw builds containing GPL demosaic packs. The GCC Runtime
  Library Exception is not a reason to reject a dependency by itself.

Historical library evaluations are in the archived plan; recheck the actual
package and optional components when adding a dependency.
