---
name: start-version
description: Start a release branch from updated main after the previous work is merged.
---

# Start version

1. Read `CLAUDE.md`, `docs/agent-collaboration.md`, `VERSION`, and the current
   `PLAN.md`. Check branch/status. Work stays in the main checkout; use a
   worktree only as `docs/agent-collaboration.md` §4 allows.
2. Preserve existing work. If the tree is dirty, ask how to carry it forward;
   stash only with authorization, include untracked files, and record the stash.
3. Switch to `main`, then `git pull --ff-only`. Confirm the preceding work is
   merged (including squash merges). If it is not, resolve that with the user
   before starting a new release; do not discard or rewrite it.
4. Use the user's release scope, otherwise the next clear planned version.
   Ask only when version or scope is ambiguous. Name the branch
   `v{version}/{short-description}` and create it from updated main.
5. Restore any authorized stash and resolve conflicts without losing work.
6. Record the branch, scope, and **In progress** status in `PLAN.md`, and mark
   the previous release merged with its PR link. Leave release
   version files unchanged until finalization. Stage changes when requested;
   starting a version does not authorize a commit, push, or PR.
7. Sweep pending outcomes (`docs/agent-collaboration.md` §8). Read the latest
   status of each entry in the **Codex review** sections of earlier plans in
   `docs/superpowers/plans/`; a later closing entry supersedes an earlier
   "pending". Report open entries compactly with the new scope: new evidence,
   relevance to this version, and overdue checks. Append outcomes that now have
   evidence on the new branch, with date and evidence. Once three releases have
   completed since an entry was created (status updates do not reset the
   count), raise it with Fred to close as inconclusive or to give an owner and a
   concrete next check. The sweep does not block unrelated work.
8. Report version/branch, the sweep result, and any work or stash still needing
   attention.
