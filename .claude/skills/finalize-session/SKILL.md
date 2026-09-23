---
name: finalize-session
description: Finalize an authorized release with documentation, version bump, checks, commit, tag, push, and PR.
---

# Finalize session

Read `CLAUDE.md` and respect the user's authorization. If commits are withheld,
prepare and stage the work, then stop before committing. A request to prepare a
future PR does not override that restriction. Never force-push.

## Prepare

1. Determine the target version from the user's scope and `PLAN.md`; resolve any
   ambiguity. Review all branch, staged, unstaged, and untracked changes.
2. Review changed code for clarity and reuse; use an available simplification
   workflow when helpful. Preserve behavior and recheck any resulting edits.
3. Bump `VERSION` and `backend/pyproject.toml` together; update `uv.lock` if its
   project metadata changes. Run `sync-docs`, including its schema/reference
   version headers.
4. Complete the release checks in `CLAUDE.md`: backend lint, format, security
   (zero medium/high findings), and tests; frontend TypeScript/production build.
   Report every security finding under step 7. For documentation changes, also
   verify links, current claims, skill structure and diff whitespace. Record
   actual results; don't mark unrun tests as passed or skip release checks.
5. New behavior needs normal/edge/failure tests, concrete assertions and pinned
   calculations for scoring changes. Check coverage when behavior changes and
   investigate regressions. Resolve failed checks before committing.
6. Review the full staged diff for scope and public-repository privacy. Stage
   only relevant files; never stage ignored files or `instructions/`. Ask about
   unrelated work only when its ownership or inclusion is genuinely unclear.
7. Flag any security findings, including pre-existing findings, to Fred for a
   decision; do not silently suppress or ignore them.

## Publish when authorized

1. Commit with a concise message explaining the change. Use the actual running
   agent's harness-provided attribution; never copy a model name or invent a
   co-author address. Pass multiline bodies through a temporary file.
2. Tag the release commit `v{version}`; if that tag exists elsewhere, resolve the
   conflict instead of moving it. Push the branch with upstream tracking. Publish
   the version tag only as part of the authorized release workflow.
3. Create a PR to `main`, or update the existing branch PR. Keep the title under
   70 characters. Describe the final scope and relevant validation; omit tool
   marketing and canned boilerplate.
4. Use `gh pr create/edit --body-file` for multiline text. Check off only items
   actually verified and name the verifier (the running agent or Fred). Leave
   necessary unperformed manual checks open; do not add irrelevant UI checks to
   documentation changes.
5. Run the available PR review workflow, or review the diff directly if none is
   available. Report findings for Fred to decide which to address. For authorized
   fixes, rerun affected checks, update docs, then commit/push within the granted
   scope. Do not rewrite published history.
6. Report the version, PR URL, verification results and outstanding findings or
   manual checks.
