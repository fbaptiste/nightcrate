---
name: finalize-session
description: Use when a work session is done and ready to commit, push, and open a PR — bumps version, runs checks, commits, pushes, opens PR
---

# Finalize Session

End-of-session workflow: simplify code, sync docs, bump version, run checks, commit, push, open PR, code review.

## Process

### 1. Determine version

- Check `VERSION` file and `PLAN.md` to identify what version was being implemented
- If unclear, ask the user before proceeding
- State the version number in the response

### 2. Code simplification

- Invoke the `simplify` skill (or follow its process if not available via Skill tool)
- This reviews recently modified code for clarity, consistency, and maintainability
- Preserves all functionality — only improves how code is written
- If changes are made, re-run checks before proceeding

### 3. Sync docs

- Invoke the `sync-docs` skill (or follow its process if not available via Skill tool)
- This updates PLAN.md, CLAUDE.md, README.md, and memory before committing

### 4. Bump version

- Update `VERSION` file to the target version
- Update `backend/pyproject.toml` version field to match
- If both already match the target, skip silently

### 5. Run all checks

Run the pre-commit checklist (all must pass before committing):

**Backend (from `backend/`):**
1. `uv run ruff check src/ tests/` — lint
2. `uv run ruff format --check src/ tests/` — formatting (fix if needed with `ruff format`)
3. `uv run bandit -r src/` — security (0 medium/high)
4. `uv run pytest` — tests

**Frontend (from `frontend/`):**
5. `npm run build` — TypeScript compilation + production build

If any check fails, fix the issue and re-run. Do not proceed to commit with failing checks.

**Test quality gate:**
- New code must include tests with edge cases and error conditions, not just happy paths
- Tests must assert specific expected values, not just ranges
- Scoring/algorithm changes need pinned regression tests with hand-computed values
- Run `uv run coverage report --include="src/nightcrate/*"` — no module should regress below its current coverage level

### 6. Commit

- Stage all relevant files (do NOT stage `instructions/` or files in `.gitignore`)
- Write a descriptive commit message summarizing the work done
- End the commit message with: `Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>`
- Use a HEREDOC for the commit message
- Tag the branch with the version number

### 7. Push

- Push the current branch to origin with `-u` flag

### 8. Open PR

- Use `gh pr create` targeting `main`
- PR title: short, under 70 chars, describes the version/feature
- PR body format:
  ```
  ## Summary
  <3-5 bullet points of what was done>

  ## Test plan
  - [x] Backend lint (ruff check) ✅ Claude
  - [x] Backend format (ruff format) ✅ Claude
  - [x] Backend security (bandit) ✅ Claude
  - [x] Backend tests (pytest — N tests) ✅ Claude
  - [x] Frontend build (tsc + vite) ✅ Claude
  - [x] Code simplification pass ✅ Claude
  - [ ] Manual UI testing — load image, verify feature works 👤 User
  - [ ] <any other user-specific test items relevant to the changes> 👤 User

  🤖 Generated with [Claude Code](https://claude.com/claude-code)
  ```

  **Test plan rules:**
  - Items verified by running commands during this session: check them off with `✅ Claude`
  - Items requiring manual user testing (UI interaction, visual verification, real data): leave unchecked with `👤 User`
  - If the user has confirmed they tested something, check it off with `✅ User`
  - Be specific about what manual testing is needed based on the actual changes (e.g., "Test aberration tab with galaxy image" not just "test UI")
  - If the branch already has an open PR, push to it instead of creating a new one

### 9. Code review

- After the PR is created (or updated), invoke the `code-review:code-review` skill with the PR number
  - e.g., `/code-review <PR-number>` or `Skill("code-review:code-review", args: "<PR-number>")`
- This runs a multi-agent code review (CLAUDE.md compliance, bug scan, git history, prior PR comments, code comment compliance)
- If the review finds issues (confidence >= 80), address them:
  - Fix the issues in code
  - Re-run checks (step 5)
  - Commit and push the fixes
  - Note the fixes in the report

### 10. Report

- State the version number that was set
- Show the PR URL
- Show the test count
- Note any code review findings and whether they were addressed

## Rules

- Never skip checks — all must pass before committing
- Never force-push
- Always ask before committing if there are unstaged changes that look like they shouldn't be committed (e.g., local config, temp files)
