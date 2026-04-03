---
name: sync-docs
description: Use when a work session is ending, before committing, or when asked to update docs — syncs PLAN.md, CLAUDE.md, and README.md to reflect actual work done
---

# Sync Docs

Update project documentation to reflect work actually done in the current session or branch.

## Process

1. **Gather changes** — Run `git diff $(git merge-base HEAD main)...HEAD --stat` and `git log --oneline $(git merge-base HEAD main)..HEAD` to understand what changed since branching from main. Also review uncommitted changes with `git diff --stat`.

2. **PLAN.md** — For the current version section:
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

5. **Memory** — Review the session for anything worth persisting to memory:
   - New user preferences or feedback → `feedback` memory
   - Project decisions or context → `project` memory
   - User profile updates → `user` memory
   - Check existing memories in `MEMORY.md` — update stale ones, don't duplicate
   - Only save things useful in future sessions, not ephemeral task details

6. **Report** — Summarize what was updated and what was skipped (with reason).

## Rules

- Never commit or push — just edit the docs
- Never modify code files
- Present a summary of proposed PLAN.md changes before making them (the user may want to adjust)
- For CLAUDE.md, only update sections that are actually stale — don't rewrite sections that are still accurate
- Be concise in checkbox descriptions — match the style of existing items in PLAN.md
