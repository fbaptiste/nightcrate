# DSO catalog architecture (v0.15.0)

## Data-source precedence

NightCrate layers multiple catalog sources onto a single `dso` table.
Order matters — each loader runs in a fixed position in the startup
sequence, and precedence is enforced structurally rather than by
cross-checks:

1. **OpenNGC + addendum** (fetched from GitHub, `catalog_loader/remote.py`)
   provide the base rows. Coordinates, type, size, and photometry fields
   on `dso` are considered authoritative from OpenNGC for the rest of
   time — no later source overwrites them.
2. **Sharpless 2** (VizieR VII/20, `catalog_loader/sharpless_loader.py`)
   and **Barnard** (VII/220A, `catalog_loader/barnard_loader.py`) add
   new DSOs. Sharpless consults `nightcrate/sharpless_crossref.csv` as a
   side-input to merge selected Sh2 identifiers onto existing OpenNGC
   DSOs (e.g. Sh2-281 → NGC 1976); unmapped Sh2 rows become standalone
   DSOs with `Sh2-<n>` as the primary designation. Barnard does not
   crossref-merge — dark nebulae and backing emission regions are
   physically distinct.
3. **NightCrate editorial augmentation**
   (`data/catalogs/nightcrate/dso_augment.csv`, loaded by
   `catalog_loader/augment_loader.py`) refines fields on existing DSOs:
   it replaces `common_name`, fills `surface_brightness` on non-galaxy
   DSOs only, and sets `distance_pc` with `distance_method = 'curated'`.
   Unresolved designations are logged at WARNING and skipped — the file
   enriches known objects, not creates new ones.
4. **50 MGC galaxy distances** (Ohlson+ 2024, J/AJ/167/31,
   `catalog_loader/mgc50_augmenter.py`) fills `distance_pc` on galaxy
   DSOs that don't yet have one, using `bestdist` (linear Mpc) from the
   50 Mpc Galaxy Catalog. The `WHERE distance_pc IS NULL` guard means a
   curated distance (step 3) is never overwritten. The file is fetched
   from the author's **GitHub mirror** (`github.com/davidohlson/50MGC`,
   default branch `master`) rather than VizieR because the CDS endpoint
   has been intermittently flaky; the underlying data is the same. The
   GitHub mirror ships a FITS binary table at `data/catalog.fits`;
   `mgc50_parser.py` reads it via astropy using lowercase column names
   (`pgc`, `bestdist`, `bestdist_error`, `bestdist_method`).
5. **Redshift-derived Hubble-law distances**
   (`catalog_loader/redshift_distance.py`) fills `distance_pc` on any
   remaining galaxy DSOs that have a non-zero redshift but no prior
   distance. Method tag is `redshift`. Non-relativistic formula
   `d = z · c / H₀` with H₀ = 70 km/s/Mpc. Not a fetched source —
   a pure post-load computation, so it always re-runs on every
   `load_catalogs` call and doesn't appear in `dso_catalog_source`.

VizieR fetches (Sharpless, Barnard) rotate through three CDS mirrors
(Strasbourg → India → South Africa) when a host exhausts its retries;
the GitHub fetches (OpenNGC, 50 MGC) use `raw.githubusercontent.com`
exclusively.

The **commit marker for every remote download is the `version.json`
file** alongside the data files — it's written LAST, so a crash
mid-rename leaves no version.json and the next boot reports the source
as "Not loaded" until the user re-fetches.

## Galaxy vs non-galaxy surface brightness

A single `dso.surface_brightness` column holds two physically different
quantities: OpenNGC measures the galaxy mean integrated over the 25
mag/arcsec² isophote, while the NightCrate augment CSV supplies the
peak brightness of iconic planetary nebulae and SNRs. The augment
loader enforces this asymmetry: non-galaxy DSOs accept the override,
galaxy DSOs ignore it with a DEBUG log. The detail panel's "augmented"
star icon disambiguates the provenance for users.

## User-facing type grouping

`services/dso_type_groups.py` is the single source of truth that maps
OpenNGC's 19 `obj_type` codes to the 13 user-facing groups (Galaxy,
Emission Nebula, Open Cluster, …). Frontend gets the grouping via the
`/api/dso/facets` response — both `raw_types` (for the Advanced Filters
expander) and aggregated `type_groups` are returned. `Cl+N` rolls up
under "Emission Nebula" deliberately: amateurs imaging NGC 2264 or
NGC 7023 are pointing at the nebulosity, not the embedded cluster.

## When to add a new catalog source

1. Add a `CatalogSource` entry in `registry.py:get_sources()`.
2. Write a new loader module in `catalog_loader/` with the same
   signature as the existing ones (`load_*(conn, source, *, force)
   -> SourceResult`).
3. Register the `parser` string in `loader.py:_dispatch_source`.
4. If the source augments (like 50 MGC) rather than creates DSOs,
   put its row count on `dso_catalog_source.row_count` as
   "DSOs updated" and document the semantic in the Admin panel.
5. Add corresponding admin endpoints + frontend UI if fetchable.
6. Update this file and `CLAUDE.md` with the new precedence position.
