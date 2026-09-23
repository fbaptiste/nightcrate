---
name: finalize-session
description: Use when a work session is done and ready to commit, push, and open a PR — bumps version, runs checks, commits, pushes, opens PR
---

# finalize-session

**Follow [`.claude/skills/finalize-session/SKILL.md`](../../../.claude/skills/finalize-session/SKILL.md).**
That file is the single source for this skill; this one is a pointer so the two
cannot drift.

Read it and do what it says, with one substitution: wherever it names a specific
agent — commit attribution, PR test-plan checkmarks, a `~/.claude/...` path —
use your own identity and your own equivalent path. See [`AGENTS.md`](../../../AGENTS.md).

If this skill needs a real change, change it in `.claude/skills/finalize-session/SKILL.md`.
