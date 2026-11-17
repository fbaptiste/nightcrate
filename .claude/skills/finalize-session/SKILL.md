---
name: finalize-session
description: Prepare a release candidate for Fred's acceptance test, then publish it once he authorizes (commit, local review, push, and the PR opened last). Release tags come from release.yml.
---

# Finalize session

Read `CLAUDE.md` and `docs/agent-collaboration.md`, and respect the user's
authorization. *Prepare* happens before Fred's acceptance test; *Publish* only
after he authorizes it. A request to prepare a future PR does not authorize
publication. Never force-push.

## Prepare (before Fred's acceptance test)

1. Determine the target version from the user's scope and `PLAN.md`; resolve any
   ambiguity. Review all branch, staged, unstaged, and untracked changes.
2. Do not refactor application code here. Route simplification or reuse
   findings to the writer during review. If preparation shows a code change is
   needed, return it to implementation and review, then prepare the candidate
   again.
3. Bump the version in all four places together: `VERSION`,
   `backend/pyproject.toml`, `frontend/package.json` (with `npm version
   <x> --no-git-tag-version`, so `package-lock.json` follows) and
   `packaging/shell/src-tauri/Cargo.toml` (then `cargo update -p
   nightcrate-shell --offline`). The installed app's shell takes its
   version from `frontend/package.json`, and `release.yml` refuses to build
   when they disagree. Update `uv.lock` if its project metadata changes.
   Run `sync-docs`, including its schema/reference version headers.
4. Complete the release checks in `CLAUDE.md`: backend lint, format, security
   (zero medium/high findings), and tests; frontend TypeScript/production build.
   Run the full backend suite once here. Report every security finding under
   step 8. For documentation changes, also verify links, current claims, skill
   structure and diff whitespace. Record actual results; don't mark unrun tests
   as passed or skip release checks.
5. New behavior needs normal/edge/failure tests, concrete assertions and pinned
   calculations for scoring changes. Check coverage when behavior changes and
   investigate regressions. Resolve failed checks before continuing.
6. Confirm the required independent reviews: a fresh Codex review for each
   high-stakes change, and one batched Codex review of material Claude-authored
   changes (`codex` skill). Resolve or take findings to Fred.
7. Review the full staged diff for scope and public-repository privacy. Stage
   only relevant files; never stage ignored files or `instructions/`. Ask about
   unrelated work only when its ownership or inclusion is genuinely unclear.
8. Flag any security findings, including pre-existing findings, to Fred for a
   decision; do not silently suppress or ignore them.
9. Update the current status of every entry in the plan's **Codex review**
   section (append only). Shipping does not make an outcome favorable.
10. Identify the candidate (branch, HEAD, and `git write-tree` of the staged
    index), set `PLAN.md` to **Candidate ready — awaiting Fred's acceptance**,
    and stop. Fred tests this candidate. A later behavior change needs the
    affected checks and renewed acceptance.

## Publish (after Fred's authorization)

The PR is opened last (Fred, 2026-11-15): "do not open the PR until the very
last moment when everything is ready". Every push to an open PR reruns the
required checks on three systems, so no PR exists while work continues, and
once it is open, further pushes are avoided.

1. Confirm the staged tree still matches the accepted candidate, or that any
   difference is version/docs metadata Fred has seen.
2. Set `PLAN.md` to **Complete — awaiting merge**. Commit with a concise
   message explaining the change. Use the actual running
   agent's harness-provided attribution; never copy a model name or invent a
   co-author address. Pass multiline bodies through a temporary file.
3. Review the committed branch diff locally, before anything is pushed:
   - run the available review workflow against the branch (not a PR);
   - cover changes made after the candidate's independent reviews, and any
     remaining findings.
   Report the findings for Fred to decide which to address. Authorized
   fixes go into a follow-up commit, with the affected checks re-run and
   the docs updated.
4. Don't tag. From v0.54.0, `release.yml` creates the version tag on the
   merged commit it builds, when Fred says "release" (spec v0.54.0 §10).
   A tag made at PR time could end up behind the merged code. Push the
   branch with upstream tracking, and verify the remote branch SHA equals
   local HEAD (`git ls-remote`).
5. **Open the PR to `main` as the last step.** Keep the title under 70
   characters. Describe the final scope and relevant validation; omit tool
   marketing and canned boilerplate. Use `gh pr create --body-file` for
   multiline text. Check off only items actually verified and name the
   verifier (the running agent, Codex, or Fred). Leave necessary unperformed
   manual checks open; do not add irrelevant UI checks to documentation
   changes.
6. Merging requires the three `checks` jobs to pass (Fred's admin override
   aside). If one fails, report it; a fix is a new commit and push to the
   open PR, within Fred's authorization. Do not rewrite published history.
7. Report the version, PR URL, check results and outstanding findings or
   manual checks.

A version that changes CI or the test setup is measured first on a throwaway
`ci/<version>` branch (which `checks.yml` runs on push), with Fred's
authorization, and the branch is deleted afterwards. The PR then opens only
once its checks are known to pass.
