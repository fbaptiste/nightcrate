# AGENTS.md

**The project instructions live in [`CLAUDE.md`](./CLAUDE.md). Read that file — it
applies to you in full, whichever agent you are.**

This file is a pointer, not a copy. It used to be an 874-line duplicate of
`CLAUDE.md`, which is a bad idea for a file whose whole job is to carry rules that
were expensive to learn: the migration policy, why the GPU backend must never be
called from a thread, why cloud is a gate and not a weighted term. When two copies
exist, a rule gets added to one of them, and whichever agent reads the stale copy
confidently reintroduces a bug the other one already fixed.

So there is one source. Everything below is the only thing that legitimately
differs between agents.

## Identity

`CLAUDE.md` and the skills are written to be agent-neutral about this, so you
generally do not need to do anything special — but to be explicit:

- **Commit and PR attribution** is whatever the harness tells you to use for the
  model actually running the session. Do not copy an attribution line out of an
  example; use your own. The `finalize-session` skill says the same thing.
- **Test-plan checkboxes** in a PR body are marked with the name of whoever
  verified the item — you, or Fred. Use your own name rather than the one in the
  example.
- **Home-directory paths** in the skills (`~/.claude/...`) refer to the Claude
  Code harness. If your harness stores session memory or commands elsewhere, use
  your own equivalent path; the intent is "this agent's own memory", not that
  literal directory.

## Skills

The project skills live in `.claude/skills/`. `.agents/skills/` holds pointers to
them for the same reason this file is a pointer. If you add or change a skill,
change it in `.claude/skills/` and leave the pointer alone.

## If you are about to fork this file

Don't. If something in `CLAUDE.md` is wrong or Claude-specific in a way that
actually matters for you, fix it there so it is fixed for everyone, or add the
narrow exception to this file. A second full copy is how the rules rot.
