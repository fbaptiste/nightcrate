# Template — implementation handoff

From: Claude. To: Codex (implementation profile). Phase <n> of <m>.

- **Approved plan and phase:** <path § phase>. Base SHA: <sha>.
- **Allowed scope:** <files/directories>. **Non-goals:** <list>.
- **Contracts:** <API shapes, types, schema, invariants>.
- **Constraints:** `CLAUDE.md`; `docs/development-decisions.md` sections <list>.
- **Fixtures:** <test data, disposable databases>.
- **Facts:** <labeled verified/assumed>.
- **Acceptance commands:** <exact commands>. If `uv run` cannot use its cache,
  use `.venv/bin/python -m pytest` and say which ran.
- **Stop conditions:** stop and report if <contradiction with the plan, needed
  dependency, schema change not in the plan, scope expansion>.

**Never:** stage, commit, push, create branches or PRs; add unplanned
dependencies; edit existing migrations; edit agent instructions, skills, or
private notes; touch real user data.

**Self-check, then report:**
1. Files changed, created, or deleted.
2. What changed and why.
3. Tests added.
4. Commands that actually ran, with exit status and key output.
5. Environment changes.
6. Deviations from the plan, and why.
7. Unverified behavior and remaining risks.
8. Open questions.
