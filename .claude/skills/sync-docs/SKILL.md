---
name: sync-docs
description: Use when a work session is ending, before committing, or when asked to update docs — syncs PLAN.md, CLAUDE.md, README.md, DB_SCHEMA.md, DB_SCHEMA_DDL.sql, LLM_DB_SPECS.md, and nightcrate-current-state.md to reflect actual work done
---

# Sync Docs

Update project documentation to reflect work actually done in the current session or branch.

## Process

**Version header:** `DB_SCHEMA.md`, `DB_SCHEMA_DDL.sql`, `LLM_DB_SPECS.md`, and `nightcrate-current-state.md` each carry a `NightCrate version: <X.Y.Z>` line near the top. Whenever the `VERSION` file or `backend/pyproject.toml` version changes (typically in the `finalize-session` bump), update these four headers to match. Markdown uses `**NightCrate version:** <X.Y.Z>`; the SQL file uses `-- NightCrate version: <X.Y.Z>`. If the headers already match the target, skip silently.

1. **Gather changes** — Run `git diff $(git merge-base HEAD main)...HEAD --stat` and `git log --oneline $(git merge-base HEAD main)..HEAD` to understand what changed since branching from main. Also review uncommitted changes with `git diff --stat`.

2. **PLAN.md** — For the current version section:
   - Update the **Table of Contents** at the top: add ✅ after the line for any version that is now complete
   - Update the version's **Status** line: `Status: Planned` or `Status: In Progress` → `Status: Done`
   - Update the version's **Branch** line if it was TBD
   - Check off (`- [x]`) completed items
   - Add new subsections for work done that wasn't originally planned (with checked boxes)
   - Update completion criteria to reflect actual state
   - Update test count if tests were added
   - Present proposed changes before editing

3. **CLAUDE.md** — Check if any of these changed:
   - New services, API endpoints, or modules added
   - Architecture patterns changed (new components, data flow)
   - New frontend components or pages
   - New dependencies or tools
   - If yes, update the relevant sections. If no changes needed, skip silently.

4. **README.md** — Check if new dependencies were added (search for new imports in `pyproject.toml` or `package.json` changes). If so, update the Open Source Acknowledgments table.

5. **DB_SCHEMA.md** — If any database tables, columns, indexes, triggers, or views changed:
   - Update the Mermaid ER diagrams to reflect the current schema
   - Update the table summary sections
   - Ensure diagrams match `DB_SCHEMA_DDL.sql` (the authoritative DDL source)
   - Bump the top-of-file `**NightCrate version:** <X.Y.Z>` line to match the current `VERSION` file
   - If no database changes were made but the version bumped, still update the version line; otherwise skip silently.

6. **DB_SCHEMA_DDL.sql** — If database migrations were added or changed:
   - Update the DDL file to reflect the complete current schema (all equipment tables, indexes, triggers, views)
   - This file should always represent the full CREATE TABLE statements for the current schema
   - Bump the top-of-file `-- NightCrate version: <X.Y.Z>` comment to match the current `VERSION` file
   - If no database changes were made but the version bumped, still update the version comment; otherwise skip silently.

7. **LLM_DB_SPECS.md** — LLM-facing seed-data reference at the repo root. If the equipment schema changed OR any seed CSV gained/lost columns:
   - Update the `## SQL Schema` block (abbreviated SQL signatures) to match the current migrations
   - Update any CSV header lists that changed (`### filter.csv`, `### camera.csv`, etc.)
   - Add new tables under "Populated" / "Minimal test data" / "Empty tables" as appropriate
   - Call out `is_mine` and any other user-managed columns that must NOT appear in seed CSVs
   - Bump the top-of-file `**NightCrate version:** <X.Y.Z>` line to match the current `VERSION` file
   - If no schema or CSV changes were made but the version bumped, still update the version line; otherwise skip silently.

8. **nightcrate-current-state.md** — Architect-facing living inventory at the repo root. If the branch shipped a new feature, a new route, a new table domain, a new external dependency, or substantially changed an existing feature:
   - Update the top-of-file `**NightCrate version:** <X.Y.Z>` line to match the current `VERSION` file
   - Update the "Last updated" and "Last full repo snapshot" dates
   - Update "Stack and runtime" version + any architecturally significant dep changes
   - Update the feature section's status tag and 2–4 sentence summary
   - Update "Schema state" migration number + domain groupings if tables were added
   - Leave "How to use this document," "Notable architectural decisions already made," "Known limitations and rough edges," and "What's NOT built yet" alone unless the work directly affects one of those sections
   - The full snapshot prompt is in `nightcrate-current-state-prompt-instructions.md` — that's the authoritative source for the section-by-section rules

9. **Memory** — Review the session for anything worth persisting to memory:
   - New user preferences or feedback → `feedback` memory
   - Project decisions or context → `project` memory
   - User profile updates → `user` memory
   - Check existing memories in the project's auto-memory `MEMORY.md` (under `~/.claude/projects/`) — update stale ones, don't duplicate
   - Only save things useful in future sessions, not ephemeral task details

10. **Report** — Summarize what was updated and what was skipped (with reason).

## Rules

- Never commit or push — just edit the docs
- Never modify code files
- Present a summary of proposed PLAN.md changes before making them (the user may want to adjust)
- For CLAUDE.md, only update sections that are actually stale — don't rewrite sections that are still accurate
- Be concise in checkbox descriptions — match the style of existing items in PLAN.md
