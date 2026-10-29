# Legacy catalog fixture

`legacy_dso.sql` captures the `dso`, `dso_designation`, and
`dso_catalog_source` rows produced by the pre-reconcile loaders at commit
`115f18f`. Its inputs intentionally include:

- two objects whose display primary is `M 7`;
- an addendum name with no recognized catalog prefix (`OTHER ORPHAN_A`);
- an addendum `B 33` that wins the designation before the Barnard row loads;
- a Sharpless number cross-reference merged onto `NGC 3`;
- `NGC 5` claiming the canonical name of the later `IC 9` row.

Regenerate from `backend/`, before making any loader changes, with:

```bash
uv run python tests/fixtures/catalogs/legacy/generate_legacy_fixture.py
```

The generator extracts the loader and migrations from base commit `115f18f` into
a temporary directory, creates a temporary database, calls those legacy loaders
in production order, normalizes timestamps for a stable diff, and writes
explicit-column inserts so the dump can be loaded after new columns with
defaults are added.
