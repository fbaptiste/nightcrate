## Appendix: Snapshot prompt for Claude Code

Hand this prompt to Claude Code periodically (every few weeks or after major work) to refresh the structural sections of this document. It updates the "Repository layout," "Implemented features," "Schema state," "Background processes," "External dependencies," and "Stack and runtime" sections, leaving the rest alone.

---

```
You are updating the file `nightcrate-current-state.md` in the project knowledge to reflect the current state of the NightCrate codebase at /Users/fbaptiste/dev/nightcrate.

Walk the repository and update the following sections of that document. Do NOT modify any other section — leave "How to use this document," "Notable architectural decisions already made," "Known limitations and rough edges," and "What's NOT built yet" untouched unless I explicitly ask. Update the "Last full repo snapshot" date at the top.

For each section, here's what to capture:

## Stack and runtime
- Backend framework and version (read pyproject.toml or requirements.txt)
- Key backend libraries (only the architecturally significant ones — astropy, fastapi, sqlalchemy, etc., not utility libraries)
- Frontend framework and version (read package.json)
- Key frontend libraries (only the architecturally significant ones)
- Database type and any current migration version
- How the app launches (entry points, scripts)
- Platform support (look for platform-specific code or build configs)

## Repository layout
- Top-level directory tree, depth 2-3 levels
- One-line description per top-level directory
- Skip node_modules, .venv, build outputs, caches, .git

## Implemented features
For each feature area listed, walk the relevant code and update:
- Status tag ([shipped] / [in progress] / [stub] / [planned])
- 2-4 sentence summary of what works today
- Note key UI screens/routes if applicable
- Note key backend endpoints if applicable
- Note any external dependencies specific to this feature

The feature areas to cover (add new ones if you find features not currently listed):
- Catalog and project management
- Equipment
- Locations
- Image viewer
- Weather
- Settings and admin
- API documentation

## Schema state
- Read the current migrations or schema definition
- Note the current schema version
- Group tables by domain (equipment, imaging, weather, etc.)
- One-line purpose per group, not per table

## Background processes and jobs
- Anything scheduled, cached, or async (Celery, APScheduler, asyncio tasks, background threads)
- Refresh cadences for any external data
- Caching layers

## External dependencies
- Third-party HTTP services NightCrate calls at runtime
- For each: what NightCrate uses it for, free vs paid, any auth required

## LLM DB specs
- Confirm `LLM_DB_SPECS.md` at the repo root reflects the current equipment/seed schema
- The file is the seed-data-authoring reference for LLMs (Claude Desktop) preparing CSVs — so when the schema or seed CSV headers change, it needs to be refreshed
- Check: SQL signatures in the `## SQL Schema` block match the actual migrations; CSV header lists in the per-table sections match the real files in `backend/src/nightcrate/data/seed/`; `is_mine` and other user-managed columns are explicitly noted as NOT seeded
- Do NOT regenerate the whole file — update only what has drifted

Be terse. Bullet points are fine. The goal is "an architect can quickly orient" not "complete documentation." If something has changed substantially since the last snapshot, that's worth highlighting briefly. If you're unsure whether to include something, lean toward including it — terse is fine, missing is not.

When you're done, save the updated file. Tell me what you changed.
```

---

## Appendix: Maintenance prompt (lightweight, for Fred)

Use this as a quick checklist when you finish a feature, before you forget about it:

1. Open `nightcrate-current-state.md`
2. Find or add the relevant feature section
3. Update the status tag
4. Write 2-4 sentences about what works now
5. Update the "Last updated" date at the top
6. Save

That's it. If it's getting more complex than this, hand it to Claude Code with the snapshot prompt instead.
