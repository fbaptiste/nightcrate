---
name: sync-docs
description: Use when a work session is ending, before committing, or when asked to update docs — syncs PLAN.md, CLAUDE.md, README.md, DB_SCHEMA.md, DB_SCHEMA_DDL.sql, LLM_DB_SPECS.md, and nightcrate-current-state.md to reflect actual work done
---

# sync-docs

**Follow [`.claude/skills/sync-docs/SKILL.md`](../../../.claude/skills/sync-docs/SKILL.md).**
That file is the single source for this skill; this one is a pointer so the two
cannot drift.

Read it and do what it says, with one substitution: wherever it names a specific
agent — commit attribution, PR test-plan checkmarks, a `~/.claude/...` path —
use your own identity and your own equivalent path. See [`AGENTS.md`](../../../AGENTS.md).

If this skill needs a real change, change it in `.claude/skills/sync-docs/SKILL.md`.
