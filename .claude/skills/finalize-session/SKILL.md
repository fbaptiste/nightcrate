---
name: finalize-session
description: Prepare a release candidate for Fred's acceptance test, then publish it (commit, tag, push, PR) once he authorizes.
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
3. Bump `VERSION` and `backend/pyproject.toml` together; update `uv.lock` if its
   project metadata changes. Run `sync-docs`, including its schema/reference
   version headers.
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

1. Confirm the staged tree still matches the accepted candidate, or that any
   difference is version/docs metadata Fred has seen.
2. Set `PLAN.md` to **Complete — awaiting merge**. Commit with a concise
   message explaining the change. Use the actual running
   agent's harness-provided attribution; never copy a model name or invent a
   co-author address. Pass multiline bodies through a temporary file.
3. Tag the release commit `v{version}`; if that tag exists elsewhere, resolve the
   conflict instead of moving it. Push the branch with upstream tracking, and
   verify the remote branch SHA equals local HEAD (`git ls-remote`). Publish the
   version tag only as part of the authorized release workflow.
4. Create a PR to `main`, or update the existing branch PR. Keep the title under
   70 characters. Describe the final scope and relevant validation; omit tool
   marketing and canned boilerplate.
5. Use `gh pr create/edit --body-file` for multiline text. Check off only items
   actually verified and name the verifier (the running agent, Codex, or Fred).
   Leave necessary unperformed manual checks open; do not add irrelevant UI
   checks to documentation changes.
6. Run the available PR review workflow for changes made after the candidate's
   independent reviews and for remaining findings. Report findings for Fred to
   decide which to address. For authorized fixes, rerun affected checks, update
   docs, then commit/push within the granted scope. Do not rewrite published
   history.
7. Report the version, PR URL, verification results and outstanding findings or
   manual checks.
