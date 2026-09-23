---
name: sync-docs
description: Update current project documentation from implemented changes, without committing or pushing.
---

# Sync documentation

Read `CLAUDE.md`. Inspect the branch diff from its merge base with `main`, its
commits, and **both staged and unstaged changes**. Verify claims against code and
migrations. Update only affected documents; a documentation cleanup may explicitly
include broader rewrites.

| Document | Update when |
|---|---|
| `PLAN.md` | Scope, completed work, verification, lifecycle status, or remaining work changes |
| `CLAUDE.md` | Shared architecture, coding rules, or workflow changes |
| `docs/agent-collaboration.md` | Fred approves a change to the Claude–Codex workflow (never edited on inference alone) |
| Plan's **Codex review** section | A tracked disagreement or rejected finding changes status (append only) |
| `docs/development-decisions.md` | A feature gains or changes a durable constraint |
| `README.md` | User behavior, setup, dependencies, or acknowledgments change |
| `docs/README.md` | Code locations or maintained documentation change |
| `DB_SCHEMA.md` / `DB_SCHEMA_DDL.sql` | Tables, columns, constraints, indexes, triggers, or views change |
| `LLM_DB_SPECS.md` | Equipment schema, seeded fields, or CSV headers change |

- Keep current facts in one place and link to details. Replace superseded text;
  do not append another contradictory release paragraph. Historical plans live
  in `docs/archive/` and are not current instructions.
- Keep planned work distinct from shipped behavior. Check off completed tasks,
  but mark a release done only when its full scope and required verification are
  complete. Do not claim a full repository audit from a narrow feature update.
- Keep `PLAN.md`'s status literal: **In progress**, **Candidate ready — awaiting
  Fred's acceptance**, or **Complete — awaiting merge**. The next
  `start-version` marks the release merged with its PR link.
- When `VERSION` and `backend/pyproject.toml` are bumped, synchronize the version
  headers in `DB_SCHEMA.md`, `DB_SCHEMA_DDL.sql`, and `LLM_DB_SPECS.md`.
  Otherwise retain their current version.
- Preserve exact schema/CSV contracts and user-managed field exclusions such as
  `is_mine`; don't shorten away constraints. Migrations determine schema truth.
- Keep README's feature summary and PLAN's remaining work consistent. Check
  implementation entry points to distinguish working features from schema-only
  placeholders; remove stale "not built" claims.
- Store lasting project decisions in shared docs; keep personal/session memory
  in the running agent's own memory system. Do not copy private facts into this
  public repository or manufacture duplicate memory entries.
- Verify local links, factual consistency, and `git diff --check` for staged and
  unstaged changes. Stage the requested files when authorized. Report the main
  updates and verification; do not change application code, commit, or push.
