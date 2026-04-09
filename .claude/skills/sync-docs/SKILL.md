---
name: sync-docs
description: Use when a work session is ending, before committing, or when asked to update docs — syncs PLAN.md, CLAUDE.md, README.md, DB_SCHEMA.md, and DB_SCHEMA_DDL.sql to reflect actual work done
---

# Sync Docs

Update project documentation to reflect work actually done in the current session or branch.

## Process

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
   - If no database changes were made, skip silently.

6. **DB_SCHEMA_DDL.sql** — If database migrations were added or changed:
   - Update the DDL file to reflect the complete current schema (all equipment tables, indexes, triggers, views)
   - This file should always represent the full CREATE TABLE statements for the current schema
   - If no database changes were made, skip silently.

7. **Memory** — Review the session for anything worth persisting to memory:
   - New user preferences or feedback → `feedback` memory
   - Project decisions or context → `project` memory
   - User profile updates → `user` memory
   - Check existing memories in the project's auto-memory `MEMORY.md` (under `~/.claude/projects/`) — update stale ones, don't duplicate
   - Only save things useful in future sessions, not ephemeral task details

8. **Report** — Summarize what was updated and what was skipped (with reason).

## Rules

- Never commit or push — just edit the docs
- Never modify code files
- Present a summary of proposed PLAN.md changes before making them (the user may want to adjust)
- For CLAUDE.md, only update sections that are actually stale — don't rewrite sections that are still accurate
- Be concise in checkbox descriptions — match the style of existing items in PLAN.md
