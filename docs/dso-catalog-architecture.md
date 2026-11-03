# DSO catalog architecture (v0.44.0)

## Object identity and reloads

Catalog reloads reconcile one complete in-memory object set instead of deleting
and recreating rows source by source. Each source row has a stable
`source_key`:

- OpenNGC: its exact `Name`;
- Sharpless, Barnard, LBN, LDN, Herbig-Haro and Melotte: the normalized
  catalog number;
- Wolf-Rayet and MCG: the canonical identifier (`101a`, `-02-05-050`);
- planetary nebulae: the HASH id;
- ACO: the cluster number, prefixed `S` for the supplementary southern table;
- Arp: the member's `Arp`, `RAJ2000`, `DEJ2000`, `Name` and `MType` strings
  joined by `:`. Webb's index sometimes gives two members one position, so
  the position alone isn't unique.

A row matched by `(source_catalog_id, source_key)` is updated in place,
preserving its `dso.id`, creation time, and every user relationship. The
one-time upgrade from older databases first pairs rows by an unambiguous
`source_row_hash`, checked across OpenNGC's main and addendum files together so
a row that moved between them keeps its identity, then within each source; for
unchanged files only, the remaining rows then pair by legacy display text in
file order. Hash first keeps two old rows that share a stored name (a corrected
false primary) from trading identities and user links.

**Identity by contribution.** A new object whose own key matches no row takes
the unclaimed old row keyed by any of its contributing keys (its own and every
entry merged into it), or failing that the row the previous `dso_source_entry`
lists for one of those keys. Exactly one candidate must match; an ambiguous
match logs a WARNING and inserts a new row. This keeps an object's id when its
owner changes: an LDN cloud merged into a Barnard object keeps that id, and the
user's links, when Barnard is removed and LDN stays. An inactive retained row
keeps its own `source_key`, so adding its catalog back matches it exactly and
reactivates it.

The object step's inputs are OpenNGC main and addendum, the Sharpless
cross-reference, the editorial augment hash, every source of an optional catalog
that is on and available, and the shipped editorial object files
(`melotte.csv`, `arp_members.csv`, `dso_parts.csv`, `dso_match_overrides.csv`).
Each file has its own `dso_catalog_source` row and hash, so changing one reruns
the step once. Designation ownership is resolved across the complete new set
before a single database transaction updates objects and rebuilds designations,
groups and source entries. OpenNGC objects claim their own parsed names before
any alternate, so an object's own designation outranks alternate-name claims
regardless of source row order.

Merges come only from explicit OpenNGC `Dup` rows, Sharpless cross-references,
an unambiguous full Barnard identifier matching an OpenNGC parsed own name, and
rule R for the catalogs added in v0.44.0 (below). Position alone never merges.
Known user links move to the survivor; an unknown future foreign key keeps the
old row inactive as a safety net. Other unclaimed rows become inactive and
retain their catalog and enrichment values. Only an explicit catalog removal
deletes objects.

Every table with a foreign key to `dso` must be classified in
`catalog_loader.user_links` as a catalog-derived table that may be rebuilt or a
user-link table whose records must move during a merge. `dso_group`,
`dso_group_member` and `dso_source_entry` are catalog-derived. A fresh-database
guard test enumerates those foreign keys and fails when a new table is
unclassified; the runtime reference count still keeps a merged row inactive if
an unknown reference reaches production.

Reload invalidation is persisted in `dso_catalog_source.file_hash`: an empty
hash means the source is due again. After an object step, augmentation and every
enrichment pass are invalidated and rerun in precedence order. A failed pass
therefore stays due after a restart. If a previously loaded object input of a
catalog that is on is missing, or an applied catalog's download is incomplete,
the object step is deferred without changing objects, while enrichment still
processes its own changes. A never-loaded absent optional source does not block
other inputs, and a removed catalog never defers. A failed object
reconciliation is reported for each object source and likewise does not
prevent independently changed enrichment from running.

## Optional catalogs

`registry.OPTIONAL_CATALOGS` lists, in Catalogs-section order, every catalog
the user may add or remove. Each `OptionalCatalog` gives its `catalog_id`,
display name, `source_ids`, `kind` (`vizier` or `nightcrate`), the
`VizierFetchSpec`s to download, the `designation_catalogs` codes it contributes,
`legacy_default`, and the `credit` shown on the page.

- OpenNGC is required and not listed: Messier, NGC, IC and Caldwell come from
  it, and every other catalog is matched against it.
- Two catalogs may share a source. `png` and `abell_pn` both read the HASH
  table, which stays on disk while either is on.
- Melotte is `kind="nightcrate"`: its list ships with the app and needs no
  download.

**The choice is app-wide,** because downloaded files are shared by every
workspace database. `catalogs/choice.json` sits beside the downloads and holds
`{"version": 1, "chosen": [...], "removed": [...]}`.
`catalog_choice.read_choice` drops unknown ids and returns `None` for a missing
or invalid file; an invalid file logs a WARNING and is left untouched.
`write_choice` replaces the file atomically. Each database records what it
applied in `dso_catalog_applied` (`on` or `removed`; no row means off).

`catalog_choice.effective_state(choice, catalog, applied)` applies these rules
in order:

1. the id is in `chosen`: on. An explicit add overrides a recorded removal;
2. the id is in `removed`: removed;
3. this database applied `on` or `removed`: that state;
4. otherwise on for `legacy_default` catalogs (Sharpless and Barnard), off for
   the rest.

**Nothing is inferred.** A lost or corrupt choice file, a missing file or
missing download metadata keeps what the database already applied. Only an
explicit `removed` entry deletes anything. Sharpless and Barnard keep their
earlier behaviour: they load whenever their files are present, until removed.

`loader.prepare_object_step` resolves these states and builds the object set;
`prepare_removal_step` does the same with the removal added to the choice.
`load_catalogs` and the removal preview therefore share one preparation and
defer for the same reasons.

- A catalog is available when `registry.optional_catalog_install` finds its
  download complete; Sharpless also needs its cross-reference file. Sources of
  catalogs that are off, removed or unavailable stay out of the object set.
- `selection_changed` makes the step run whatever the file hashes. It is set
  by any catalog whose effective state differs from its applied row (no row
  counts as off), unless that catalog is on but unavailable. Switching `png`
  off while `abell_pn` stays on therefore reruns the step with the shared file
  unchanged. A fresh install without the Sharpless or Barnard files never
  triggers it.
- After the step, `dso_catalog_applied` records `on` for each catalog included
  and `removed` for each removal applied, and loses the rows of catalogs that
  are off. An unavailable catalog's row is left as it was.

A database opened later applies the same choice once, including a removal.

## Removing a catalog

`POST /api/admin/catalogs/optional/{catalog_id}/remove` first runs the removal
as a dry run (`loader.prepare_removal_step`, then `apply_object_set(...,
dry_run=True)`); `GET .../removal-preview` returns the same counts for the
confirmation dialog. A deferred step blocks the removal with 409. Otherwise the
removal is written to `choice.json`, the catalog's VizieR files that no catalog
still on shares are deleted, and the loader runs.

`apply_object_set` deletes an unclaimed object only with positive evidence that
removed catalogs alone provided it:

- it has `dso_source_entry` rows, and every one belongs to a removed catalog;
  or
- it has none (rows from before migration 0066, or keyless retained rows), and
  every catalog of its own source is removed.

An empty set is never evidence. Such an object is then:

- **deleted** when nothing outside the catalog-derived tables references it,
  ignoring `project_dso`. Its `project_dso` rows are deleted first; its
  designations, groups, source entries, external references and thumbnails
  cascade.
- **kept inactive** when `favorite_target`, `project_target` or an unclassified
  table references it. It keeps its `source_key` and every old name no current
  object claims.

`project_dso`, a solve's in-frame list, is not a link. It is computed when the
solve is made, and its main-target flag comes from `project_target`. Counting
it would keep thousands of inactive MCG galaxies from galaxy-field solves after
MCG is removed. Merges still move its rows through `user_links`.

An object another loaded catalog also provides stays, with that catalog's
values. It loses the names only the removed catalog gave it, such as a
Sharpless number added through the cross-reference. Names that OpenNGC lists
among the object's alternates stay, because OpenNGC claims them whatever is on.
Adding the catalog back reactivates the kept objects with the same ids and
links, through their retained keys and identity by contribution.

## Source entries

`dso_source_entry` has one row per contributing catalog entry, keyed by
`(source_catalog_id, source_key, catalog_id)`, pointing at the object it
resolved to. The logical `catalog_id` is part of the key because one source row
can belong to two catalogs: a HASH row named `Abell n` is in both `png` and
`abell_pn`. A merged entry is recorded on the object it merged into.

The table is rebuilt in each step. A retained inactive row keeps its previous
entries, or one per catalog of its own source when it has none; a keyless
retained row gets none. Removal reads this table as its evidence, and identity
by contribution uses it to follow an object through remove and re-add.

## Publishing VizieR downloads

`vizier.fetch_vizier_tables` downloads all of a catalog's tables and publishes
them as one commit:

1. each table is downloaded to `vizier/.download/`, trying the mirrors
   that answered the last check, and must parse as a VizieR TSV with its spec's `required_columns`;
2. a marker, `vizier/publishing/{catalog_id}.json`, lists the files;
3. the staged files replace the installed ones;
4. `vizier/version.json` gains their entries (sha256, fetch date, URL) in one
   atomic write. This is the commit point;
5. the marker is deleted.

If any table fails on every mirror, nothing is published and the installed
files stay. `registry.optional_catalog_install` treats a catalog as incomplete
while its own marker, or a marker naming one of its files, exists, or while any
file is missing or differs from its `version.json` sha256. The loader consumes
only complete catalogs. Sharpless and Barnard alone also accept a present file
with no `version.json` entry, as installed before v0.44.0. Removal deletes the
marker, the unshared files and their `version.json` entries.

VizieR fetches use six hosts: Strasbourg, then the CfA Harvard and IDIA South
Africa mirrors over HTTPS, then Tokyo, Beijing and India over plain HTTP.
Before a table, if no check has run in the past hour, all six are asked for one
Sharpless row at once (10 s limit), and those that don't answer are skipped
for the hour. The download then makes one pass over the hosts that answered;
each gets the shared HTTP client's single retry and a 10 s connect limit. A
failed request, an error status, or a body that isn't a VizieR TSV moves on to
the next host, and a transport error or HTTP 5xx also marks that host down.
`version.json` records the URL that served the data. When checked on
2026-11-03, only Strasbourg and Harvard carried HASH (V/163), and both were
down.

The GitHub fetches (OpenNGC, 50 MGC) use `raw.githubusercontent.com`
exclusively. Their commit marker is the `version.json` file alongside the data
files: it's written last, so a crash mid-rename leaves no `version.json` and
the next boot reports the source as "Not loaded" until the user re-fetches.

## Collectors and rule R

Each optional catalog after Barnard has a pure collector in
`catalog_loader/<id>_loader.py`: `collect_<id>(sources, on_catalogs) ->
CollectorBatch`.

- `reconcile.build_object_set` calls each collector once, with all of that
  catalog's sources whose files exist: WR's two tables, ACO's three, MCG's two,
  and Arp's table with the reviewed member list.
- `COLLECTOR_ORDER` fixes ownership after OpenNGC, Sharpless and Barnard:
  Melotte, WR, HH, PN, Abell PN, LBN, LDN, ACO, MCG, then Arp.
- `OBJECT_COLLECTORS` registers each collector under its first logical catalog
  id; `png` covers both HASH catalogs. A collector missing from
  `COLLECTOR_ORDER` fails at import.
- Collectors leave `constellation` empty. `build_object_set` fills every missing
  constellation at the end in one batched call
  (`astronomy.constellations_for_coords`).

A `CollectorBatch` holds `objects`, `groups` and `source_hashes`, one hash for
each source the collector read. Each `CollectedObject` carries:

- `source_id`, `source_key` and its logical `catalog_id`, plus
  `also_catalog_ids` for an entry in two catalogs;
- `catalog`/`identifier`, its own designation, or `None` for an Arp member
  with no name;
- `columns`, the `dso` values used if it becomes its own object;
- `extra_designations`, further names it claims;
- `cross_identifications`, designations a catalog column says it is;
- `evidence`, and the optional `match_size_arcmin`, `match_size_ratio_max`,
  `require_match` and `release_designations` described below.

Each `CollectedGroup` gives `catalog` and `identifier`, the `whole_key` of its
own row (a `(source_id, source_key)` pair, or `None`), `member_keys` for
members from the same batch, and `member_designations` for members found
through whoever owns those names (the Barnard objects an LDN cloud names).

A row whose catalogs are all off is skipped. Every row with a designation
resolves through **rule R**, in this order:

1. **Override:** a `dso_match_overrides.csv` row for its designation. `assign`
   merges it into the target's owner. `separate`, or an `assign` whose target
   isn't loaded, makes it a standalone object.
2. **Own name already owned,** by an OpenNGC alternate or an earlier catalog:
   merge into that owner.
3. **Cross-identification:** merge into the owner of the first
   `cross_identifications` designation that is owned.
4. **Otherwise** a standalone object with its own designation as primary.

**Options:**
- **Size gate.** With `match_size_ratio_max` set, step 3 also needs both sizes
  known and within that ratio. `match_size_arcmin` gives the entry's size when
  it has none of its own. LDN gives the equivalent diameter `2·√(Area/π)·60′`,
  used only for this test and never stored, with a ratio of 3; MCG gates NGC
  and IC names the catalog marks as uncertain the same way.
- **`require_match`** drops a row that would be standalone: a Melotte row that
  names its target only adds `Mel n` to that object.
- **`release_designations`** frees a designation from its earlier owner before
  the row resolves. An Arp number with several members releases OpenNGC's
  `Arp n` alternate so that it becomes a group.

**Merged entries add names and provenance only.** A merged entry adds its
designation, its extra names and its source entry to the owner, never columns
or notes: LBN 667 on IC 1848 keeps IC 1848's values. Every merge records a
`StatedMatch` for the match screen.

**Overrides take precedence** over a match a catalog or OpenNGC states
(`designation,action,target_designation,notes`).
- Each override's designation is reserved: no other claim, such as an OpenNGC
  alternate, can take it, whatever catalogs are on. Only the override's own
  resolution does.
- `LBN 191,separate`: the LBN catalogue and OpenNGC both name NGC 6960, only
  the Western Veil, but LBN 191 is the whole Cygnus Loop.
- An `assign` row whose designation no loaded entry owns is an alias. It adds
  that name to the target while the optional catalog contributing the
  designation's code is on (`Abell 50` on NGC 6742).

## Groups ("part of")

`dso_group` holds a catalog entry that covers several objects, and
`dso_group_member` its members. `whole_dso_id` is set when the entry is also an
object of its own (LBN 191, the whole Cygnus Loop), and NULL when it is only a
view of its members (Arp 244: NGC 4038 and NGC 4039). Groups come from:

- `dso_parts.csv` (`whole_designation,part_designation,notes`), applied after
  every collector. A row counts only when both designations resolve, and the
  group takes the whole's primary designation;
- LDN: a cloud naming several Barnard objects, or one that fails the size
  gate, is the whole, with the loaded Barnard objects as members. With Barnard
  off there is no group;
- Arp: a number with several distinct members becomes a group with no whole. A
  one-member number is a designation of that galaxy instead.

Members are pruned before writing. Unresolved members, such as those of a
catalog that is off, are dropped. The whole is never its own member, duplicates
collapse, and a group left with no members isn't written. Both tables are
catalog-derived and rebuilt in each step.

In the API (`api/dso.py`, shared with the planner):
- a search for a group's name, or for its whole's designation or common name,
  returns the members;
- catalog filters and facet counts include group members. A member with no
  name of its own in the selected catalogs displays the group's name;
- the detail panels show "Part of" and "Includes" chips, and the catalog table
  shows "Part of" pills before the other names.

## Match screen

`python -m nightcrate.catalog_loader.match_review <catalogs_root>` builds the
object set with every optional catalog on and prints, as CSV, the stated
matches that need review:
- `size_ratio`: both sizes are known and differ by more than 3× either way;
- `target_is_part`: the target is listed as a part in `dso_parts.csv`.

Each flag carries the match's evidence (`OpenNGC alternate`, `catalog column`,
`reviewed list` or the earlier catalog). Every new catalog is screened on its
full download, with the other catalogs present, before it is first applied to
any database. Each confirmed error becomes an override.

## Data-source precedence

NightCrate layers multiple catalog sources onto a single `dso` table.
Order matters — each loader runs in a fixed position in the startup
sequence, and precedence is enforced structurally rather than by
cross-checks:

1. **OpenNGC + addendum** (required; fetched from GitHub,
   `catalog_loader/remote.py`) provide the base rows. Coordinates, type,
   size, and photometry fields on `dso` are considered authoritative from
   OpenNGC for the rest of time — no later source overwrites them.
2. **Sharpless 2** (VizieR VII/20, `catalog_loader/sharpless_loader.py`)
   and **Barnard** (VII/220A, `catalog_loader/barnard_loader.py`) are
   optional catalogs that are on by default. Sharpless consults
   `nightcrate/sharpless_crossref.csv` as a side-input to merge selected Sh2
   identifiers onto existing OpenNGC DSOs (e.g. Sh2-281 → NGC 1976); unmapped
   Sh2 rows become standalone DSOs with `Sh2-<n>` as the primary designation.
   Barnard rows normally stay separate because dark nebulae and backing
   emission regions are physically distinct; they merge only when the full
   normalized identifier unambiguously matches an OpenNGC object's own parsed
   Barnard name, never an alternate. Rule R does not apply to them.
3. **The other optional catalogs**, in `COLLECTOR_ORDER`, each through rule R:
   Melotte (NightCrate's own list), Wolf-Rayet stars (VizieR III/215),
   Herbig-Haro objects (V/104), planetary nebulae and Abell planetary nebulae
   (HASH, V/163), LBN (VII/9), LDN (VII/7A), ACO galaxy clusters (VII/110A),
   MCG (VII/62A and VII/100) and Arp (VII/192). A merged entry never changes
   its owner's values. A standalone entry supplies its own, and any value that
   isn't the object's own V magnitude or visual size stays in its notes: the
   Wolf-Rayet narrow-band v, ACO's tenth-brightest-member `m10`, the LDN area.
   Melotte's new clusters store twice Hunt & Reffert's half-member radius as
   their size, labelled in the list's notes.
4. **Reviewed aliases and parts:** `assign` overrides without a loaded entry
   add their names, then `dso_parts.csv` adds its groups.
5. **NightCrate editorial augmentation**
   (`data/catalogs/nightcrate/dso_augment.csv`, loaded by
   `catalog_loader/augment_loader.py`) refines fields on existing DSOs:
   it replaces `common_name`, fills `surface_brightness` on non-galaxy
   DSOs only, and sets `distance_pc` with `distance_method = 'curated'`.
   Unresolved designations are logged at WARNING and skipped — the file
   enriches known objects, not creates new ones. A row whose designation
   belongs to an optional catalog that isn't on logs at DEBUG instead.
6. **50 MGC galaxy distances** (Ohlson+ 2024, J/AJ/167/31,
   `catalog_loader/mgc50_augmenter.py`) fills `distance_pc` on galaxy
   DSOs that don't yet have one, using `bestdist` (linear Mpc) from the
   50 Mpc Galaxy Catalog. The `WHERE distance_pc IS NULL` guard means a
   curated distance (step 5) is never overwritten. A rerun first clears active
   50 MGC and lower-precedence redshift values, while inactive objects retain
   their history. The file is fetched
   from the author's **GitHub mirror** (`github.com/davidohlson/50MGC`,
   default branch `master`) rather than VizieR because the CDS endpoint
   has been intermittently flaky; the underlying data is the same. The
   GitHub mirror ships a FITS binary table at `data/catalog.fits`;
   `mgc50_parser.py` reads it via astropy using lowercase column names
   (`pgc`, `bestdist`, `bestdist_error`, `bestdist_method`).
7. **Redshift-derived Hubble-law distances**
   (`catalog_loader/redshift_distance.py`) fills `distance_pc` on any
   remaining galaxy DSOs that have a non-zero redshift but no prior
   distance. Method tag is `redshift`. Non-relativistic formula
   `d = z · c / H₀` with H₀ = 70 km/s/Mpc. Not a fetched source —
   a pure post-load computation, so it always re-runs on every
   `load_catalogs` call and doesn't appear in `dso_catalog_source`.

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
the 22 `obj_type` codes to the 15 user-facing groups (Galaxy, Galaxy
Cluster, Emission Nebula, Herbig-Haro Object, …). Frontend gets the grouping
via the `/api/dso/facets` response — both `raw_types` (for the Advanced Filters
expander) and aggregated `type_groups` are returned. `Cl+N` rolls up
under "Emission Nebula" deliberately: amateurs imaging NGC 2264 or
NGC 7023 are pointing at the nebulosity, not the embedded cluster.
Wolf-Rayet stars (`WR*`) join "Star / Multiple".

## When to add a new catalog source

For a catalog that creates objects:

1. **Registry.** Add a `CatalogSource` per file in `registry.py`
   (`_vizier_sources`, or `_nightcrate_sources` for a shipped list), with the
   parser named after the catalog and its citation plus `CDS_CITATION` as the
   attribution. Add an `OptionalCatalog` to `OPTIONAL_CATALOGS` with its
   `VizierFetchSpec`s, `designation_catalogs` and `credit`. In each spec,
   `column_filter` lists only the columns used, `required_columns` the columns
   the collector reads, and `-out.add=_RAJ2000,_DEJ2000` goes only on tables
   with coordinates. The Catalogs section and the add/remove endpoints read
   `OPTIONAL_CATALOGS`, so no new endpoint is needed.
2. **Object inputs.** Add the source ids to `reconcile.OBJECT_SOURCE_IDS`
   (`EDITORIAL_OBJECT_SOURCE_IDS` for a shipped file) and to `load_order` in
   `loader._prepare_object_step`.
3. **Collector.** Write a pure `collect_<id>` returning a `CollectorBatch`,
   register it in `OBJECT_COLLECTORS`, and place its catalog id in
   `COLLECTOR_ORDER`. Keep missing values missing; anything that isn't the
   object's own V magnitude or visual size goes in the notes.
4. **Vocabulary.** New designation codes or object types need a forward
   migration that widens the CHECKs, as 0066 did by rebuilding `dso` and
   `dso_designation`. Change with it: `loader._DISPLAY_PREFIX`,
   `crossref_parser.PREFIX_MAP`, `designations.py` for structured identifiers
   or long names, `services/dso_type_groups.py`, `services/dso_display.py`,
   and the frontend's `catalogNames.ts` and `dsoTypeNames.ts`.
5. **Tests.** Cut a fixture of about 40 rows at most from a real download,
   keeping its VizieR header block, as
   `tests/fixtures/catalogs/vizier/mini_<id>.tsv` (one per table). In
   `tests/catalog_loader/test_<id>_loader.py`, cover the collector, a
   reconciliation against the mini OpenNGC fixture, and loads with the catalog
   on, removed and added back. Tests never touch the network.
6. **Match screen.** Run `match_review` on the full download before the
   catalog is first applied to any database. Check each flag against SIMBAD,
   and record each confirmed error as an override.
7. **Credits.** Add a README "Data Sources" row; the `credit` appears on the
   Catalogs section and the attribution in the attribution panel.
8. If any new table references `dso`, classify it as catalog-derived or
   user-linked and extend merge and removal handling before the foreign-key
   guard can pass.
9. Update this file.

For an enrichment source instead, implement its transactional loader, register
the `parser` string in `loader.py:_dispatch_source`, and add it to the persisted
invalidation order. If it augments (like 50 MGC) rather than creates DSOs, put
its row count on `dso_catalog_source.row_count` as "DSOs updated" and document
the semantic in the Admin panel.
