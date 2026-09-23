---
name: start-version
description: Start a release branch from updated main after the previous work is merged.
---

# Start version

1. Read `CLAUDE.md`, `VERSION`, and the current `PLAN.md`. Check branch/status.
2. Preserve existing work. If the tree is dirty, ask how to carry it forward;
   stash only with authorization, include untracked files, and record the stash.
3. Switch to `main`, then `git pull --ff-only`. Confirm the preceding work is
   merged (including squash merges). If it is not, resolve that with the user
   before starting a new release; do not discard or rewrite it.
4. Use the user's release scope, otherwise the next clear planned version.
   Ask only when version or scope is ambiguous. Name the branch
   `v{version}/{short-description}` and create it from updated main.
5. Restore any authorized stash and resolve conflicts without losing work.
6. Record the branch, scope, and **In progress** status in `PLAN.md`. Leave release
   version files unchanged until finalization. Stage changes when requested;
   starting a version does not authorize a commit, push, or PR.
7. Report version/branch and any work or stash still needing attention.
