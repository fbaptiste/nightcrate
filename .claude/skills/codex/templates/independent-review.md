# Template — independent review

From: Claude. To: Codex (review profile, fresh session, read-only).

- **What to review:** everything since the merge base, including uncommitted
  work: `git diff "$(git merge-base main HEAD)"` (committed, staged, and
  unstaged changes) plus the untracked files listed by
  `git status --porcelain --untracked-files=all`. Base SHA <sha>.
- **Intent:** <approved plan § phase, or the reason for a Claude-authored change>.
- **Why this review is required:** <high-stakes category | material Claude-authored change>.
- **Constraints:** `CLAUDE.md`; `docs/development-decisions.md` sections <list>.
- **Facts:** <labeled verified/assumed>.

Report findings as **blocker**, **major**, or **minor**, each with `file:line`,
the failure scenario, and a proposed fix. Name tests that would pass while
missing the defect. Say what you could not verify. Do not rely on the writer's
report. Read-only; modify nothing.
