---
name: start-version
description: Use when a PR has been merged and you're ready to start work on the next version — checks out main, pulls latest, creates a new feature branch
---

# Start Version

Post-merge workflow: ensure clean state, update main, create a new branch for the next version.

## Process

### 1. Check clean state

- Run `git status --short` to check for uncommitted changes
- If there are uncommitted changes, warn the user and ask how to proceed (stash, commit, or abort)
- Do not proceed with dirty working tree unless the user explicitly says to stash

### 2. Stash if needed

- If the user approves stashing: `git stash --include-untracked`
- Note this in the report so the user remembers to pop later

### 3. Checkout main and pull

- `git checkout main`
- `git pull`
- Verify the merge commit is present (the PR should be merged). If not found, warn the user and ask how to proceed (wait for merge, check PR status on GitHub, or abort)

### 4. Determine next version

- Check `PLAN.md` for the next planned version section (look for `## v*` sections with `Status: Planned`)
- If a clear next version exists, propose it to the user
- If unclear or multiple candidates, ask the user which version to start
- State the version number in the response

### 5. Create branch

- Branch naming convention: `v{version}/{short-description}`
  - e.g., `v0.6.0/session-ingestion`, `v0.5.1/heatmap-view`
- The short description should come from the version's goal in PLAN.md
- If unclear, ask the user for the branch name
- `git checkout -b {branch-name}`

### 6. Pop stash if applicable

- If changes were stashed in step 2: `git stash pop`

### 7. Report

- State the new branch name
- State the version being started
- Briefly note what's planned for this version (from PLAN.md)
- Remind about any stashed changes if applicable
