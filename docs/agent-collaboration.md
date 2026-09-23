# Agent collaboration — Fred, Claude, and Codex

*Approved by Fred on 2026-09-22 after four rounds of Claude–Codex review.*

`CLAUDE.md` applies to every agent; this document adds roles, gates, and
records for work Claude orchestrates. When Fred works with either agent
directly, that agent follows `CLAUDE.md` and Fred's instructions. Changing this
document needs Fred's approval after Claude consults Codex.

## 1. Roles

| | Owns | Never |
|---|---|---|
| **Fred** — product manager | Scope, priorities, product decisions, material tradeoffs. Approves the spec, the final plan, the release candidate, and every commit, push, and merge. Decides unresolved Claude–Codex disagreements. | — |
| **Claude** — lead engineer | Brainstorming with Fred; spec and implementation plan; UI design (`frontend-design`); running Codex; environment and dependency provisioning; diff review and gate re-runs; rendered UI checks; planning and docs; investigation; narrow, understood fixes; staging; delivery within Fred's authorization; private notes (§9); review records. | Accepting an unsupported completion claim or skipping independent verification; leaving a material disagreement unresolved without taking it to Fred. |
| **Codex** — senior IC | Critique of plans, including product opinions; implementation of approved plans, backend and UI; independent review of high-stakes and material Claude-authored changes. | Staging, commits, pushes, branches, PRs; private-note edits; unplanned dependency additions; editing existing migrations; editing agent instructions, skills, or this document unless that is the assigned task. |

Approved dependency or lockfile changes may be assigned to Codex explicitly
after license review.

## 2. Pipeline

| # | Stage | Owner | Gate to advance |
|---|---|---|---|
| 0 | `start-version`, including the pending-outcome sweep (§8) | Claude | Fred authorizes the version |
| 1 | Brainstorm → spec in `docs/superpowers/specs/` (`superpowers:brainstorming`; `frontend-design` for UI) | Claude with Fred | Fred approves the spec |
| 2 | Implementation plan in `docs/superpowers/plans/` (`superpowers:writing-plans`): phases, contracts, acceptance commands, high-stakes flags. Snapshot spec + plan and base SHA as the **baseline**. | Claude | Baseline frozen |
| 3 | Plan discussion, at most 5 batched rounds | Claude ↔ Codex | Converged (§3) |
| 4 | Landing report | Claude | **Fred approves the final plan**; decisions taken one at a time |
| 5 | Implementation, one phase at a time | Codex | Work left unstaged; report delivered |
| 6 | Review per phase, plus a fresh Codex review for high-stakes work | Claude (+ Codex) | Claude re-ran checks; accepted work staged |
| 7 | Rendered checks for UI changes, including tablet and accessibility behavior | Claude | Affected flows exercised |
| 8 | Candidate preparation (`finalize-session` *Prepare*): `sync-docs`, version files, full checks, batched Codex review of material Claude-authored changes | Claude | Candidate identified; checks recorded |
| 9 | Acceptance test on the prepared candidate | Fred | Fred accepts; a later behavior change needs affected checks and renewed acceptance |
| 10 | Publish (`finalize-session` *Publish*): commit, tag, push, PR | Claude | Fred's authorization; remote branch SHA equals local HEAD |
| 11 | Merge | Fred | Outcome states updated (§8) |

Fred may test phases earlier. One authorization may name several delivery
actions. Plan approval does not authorize publication.

## 3. Plan discussion (stages 3–4)

- Profile: `gpt-6-astra`, `xhigh`, read-only. Each discussion starts a fresh
  session under the full §10 profile; later rounds resume it by UUID with the
  settings reasserted. Resuming does not reset the tools or context a session
  started with.
- **Independent plan review** (default). Round 1 receives the spec, the plan,
  the review criteria, and labeled facts. Fred's approved decisions are marked
  as constraints: they change only by Fred's decision, but Codex still flags
  contradicting evidence or risks. Codex checks the plan against the code and
  reports blockers, major and minor findings, and product opinions.
- **Blinded pre-pass** (when the plan hinges on an open architectural or product
  choice). Round 1 receives the requirements, constraints, and evidence without
  Claude's answer; the frozen plan follows in round 2. The landing report names
  the mode used.
- Claude checks every finding against the code, then answers all open points in
  one batch: **accept** (with the plan change), **reject** (with evidence), or
  **counter**.
- **Converged** means every material finding is resolved, explicitly deferred,
  or presented to Fred as a disagreement. Agreement is not required. Stop early
  when converged. More than five rounds needs Fred's permission and a reason.
- **Landing report.** Always:
  1. Verdict and recommendation, with the baseline identifier and review mode.
  2. One table of changes and dispositions: section, original, final, reason and
     evidence, raised by.
  3. Material findings Claude rejected, with the evidence, and every unresolved
     disagreement, each position stated by its owner, Codex quoted. Minor
     rejected findings are counted, with a link to the local record that lists
     every disposition.
  4. Decisions for Fred, each with a recommendation and reason, asked one at a time.

  When applicable: unchanged commitments, the verification plan, and claims
  still unverified. A small release gets a short report.

## 4. Implementation (stages 5–8)

- Profile: `gpt-5.6-sol`, `high`, workspace-write, web search disabled, in the
  main checkout on the version branch. **One active writer.** A worktree is used
  only for concurrent work or risky experiments, with a named integration owner.
- Claude provisions dependencies and the environment before the handoff.
- **Handoff packet:** approved plan and phase; base SHA; allowed scope and
  non-goals; contracts; relevant `docs/development-decisions.md` sections;
  fixtures; labeled facts; acceptance commands; stop conditions; the "never"
  list; the report format.
- **Codex report:** files changed, created, or deleted; what and why; tests
  added; the commands that actually ran, with results; environment changes;
  deviations from the plan and why; unverified behavior; remaining risks; open
  questions. The writer self-checks before reporting; that self-check does not
  replace independent review.
- **Claude review:**
  1. Before the run, record Git's tracked and untracked inventory plus a private
     manifest of ignored files outside listed regenerable directories (path,
     type, mode, symlink target, content digest).
  2. After the run, diff both inventories against the handoff scope. Deletions
     and out-of-scope changes are findings.
  3. Read the full diff and the surrounding callers against the plan, checking
     acceptance criteria, failure paths, and test assertions.
  4. Re-run targeted checks: ruff, format, bandit, pytest on affected modules,
     and `npm run build` for frontend changes.
  5. Stage accepted work. The index holds Claude's last reviewed contents; later
     edits need renewed review, and candidate verification covers the whole
     worktree.
  6. Send findings to the writer session in one batch. Simplification findings
     go to the writer too; candidate preparation does not refactor application
     code. A cycle is one consolidated review, fixes, and re-review. After three
     cycles with unresolved findings, stop the phase and tell Fred the recurring
     cause, remaining risk, and recommended next step.
  7. A material disagreement during implementation or review (Codex's report,
     the writer's objection to a finding, or an independent review) goes to Fred
     and is logged under §8 like a plan-review disagreement. The affected work,
     and any work whose correctness depends on the decision, is not staged
     until Fred decides; independent work may continue. If that separation
     cannot be justified, the whole phase waits. A disagreement found after
     staging removes the affected contents from the release candidate until it
     is resolved; the working changes are preserved.
- **Frontend:** Claude designs the UI in the spec and plan; Codex implements;
  Claude owns rendered interaction checks. Fred is not the frontend reviewer.
- Use disposable databases for tests; real user data stays outside writable roots.

## 5. High-stakes work

A change is high-stakes if it touches:

- migrations or schema;
- destructive or bulk writes to user records, orphan sweeps, or cache eviction;
- seed data, the seed loader, or seed hashing;
- mutation or deletion of source files; archive extraction; path handling;
- subprocesses such as ASTAP;
- concurrency: process pools, GPU backends, threads, async ordering;
- backend–frontend contracts (Pydantic models, TypeScript types, API routes);
- dependencies, lockfiles, licensing, and external data sources and their terms;
- privacy or network exposure: LAN mode, bind addresses, CORS, outbound HTTP,
  anything that could publish private data;
- scientific calculations that change imaging decisions.

High-stakes work gets a fresh read-only Codex review (`gpt-5.6-sol`, `high`)
before Fred's acceptance test, and a check that executes the changed path:
upgrades of database copies at the preceding migration plus fresh databases
with preservation, integrity, and foreign-key assertions; independently
calculated examples for scientific changes; real-data runs; or rendered checks
for UI contracts. Size does not matter. Raw SQL alone does not make a change
high-stakes, and neither does NightCrate's own release metadata (version files
and the lockfile's project-version entry). Any change to dependency versions,
sources, resolution, or licensing is high-stakes.

## 6. Escape hatches

Planning may be abbreviated only when Claude names one of these, with the
reason, in one line: Fred says so · read-only investigation · documentation or
formatting with no behavior change · a narrow, understood fix · revert of
reviewed work · containment Fred directs, with deferred review recorded.
No hatch grants delivery permission or removes relevant verification. Material
Claude-authored changes are batched into one Codex review before Fred's
acceptance test. High-stakes work keeps its checks under every hatch.

## 7. Standing rules

1. **Codex never changes delivery state.** Every Codex run uses the profiles in
   §10. The tested combinations and their limits are listed there.
   `--ignore-rules` prevents inherited execpolicy allowances; it does not by
   itself establish every filesystem or tool restriction. Canaries are re-run
   after Codex CLI or policy changes.
2. **A Codex report is a claim.** Claude re-runs the gate and reads high-stakes
   files directly. Unrun tests are not evidence.
3. **Disagreement is surfaced.** Claude may reject findings with evidence.
   Material rejections appear in the landing report and are logged with
   outcome states (§8); minor ones are counted there and listed in the local
   record. Unresolved material disagreements, from any stage, go to Fred for
   decision, with Codex quoted.
4. **Label facts.** Claude marks decision-relevant factual claims given to Codex
   verified (with how) or assumed; stable context can share one provenance
   statement. An absence claim cites the search command and its scope.
5. **Check before relaying.** Claude opens what a Codex finding cites before
   presenting it to Fred; otherwise it is labeled unverified.
6. **Independent review is fresh.** Required reviews run in a fresh session,
   separate from the writer's.
7. **Fixed profiles.** Only Fred changes the models or effort levels. If Codex
   cannot run, Claude reports the gap and its consequence, continues only
   independent work already authorized, and does not substitute another model
   or reviewer silently. Fred decides whether to wait, narrow scope, or approve
   another approach.
8. **Web sources.** Planning may use web search with primary sources cited and
   version/date applicability recorded. A source can verify a documentary
   claim; NightCrate's behavior needs repository or runtime evidence. Private
   project data stays out of queries.

## 8. Records

- The spec and plan are tracked and committed with the release.
- The plan gets a short, sanitized **Codex review** section: review mode, rounds
  used, adopted changes, and one entry per tracked item, each with a stable ID
  (for example `v0.42.0-D1`). Tracked items are:
  - material disagreements from any stage — plan discussion, implementation,
    or review — with both positions, Codex quoted, the evidence, and Fred's
    decision;
  - material Codex findings Claude rejected, with the evidence, so a wrong
    rejection can be found later.
- Each entry has three fields, not a required sequence: **disposition**
  (what was chosen, or "rejected"), **implementation** (done, partial, or
  "n/a — no change"), and **outcome** (supported, contradicted, inconclusive, or
  pending with an owner and next check). The original finding and rationale are
  kept. Agreement with a rejection's reasoning does not validate it, and failing
  to reproduce a problem does not disprove it. Status changes are appended with
  the date and evidence; earlier text is not rewritten. Finalization updates the
  current status; shipping does not make an outcome favorable.
- Outcomes are appended whenever evidence appears during authorized work.
  **Every `start-version` also sweeps** the latest status of each entry in
  earlier plans (a later closing entry supersedes an earlier "pending") and
  reports the open ones to Fred compactly, highlighting new evidence, relevance
  to the new scope, and overdue checks. An entry still pending after three
  releases completed since it was created (status updates do not reset the
  count) is raised with Fred to close as inconclusive or give an owner and a
  concrete next check. This does not block unrelated version work.
- Raw rounds, handoffs, reports, and manifests go in `.superpowers/codex/<version>/`
  (ignored, local).
- After three versions, Claude and Fred review time cost, useful defects found,
  escaped defects, rework, and unresolved outcomes, and drop rules that add
  friction without demonstrable benefit. A tally of decisions does not measure
  which model "won".

## 9. Private notes

Fred's private project notes are described in `CLAUDE.local.md` when present.
In Claude-orchestrated work, Claude is the only writer of those notes. Codex
launched by Claude never writes them; it reports proposed lasting findings
instead. The review brief names the notes a
reviewer reads and any exclusions. Reviewers receive settled constraints, with
their source and approval status explicit, and do not read speculative
positions on the question under review before recording their initial
assessment. When a review reconsiders a recorded decision, the brief discloses
that prior position.

## 10. Command profiles (codex-cli 0.156.0)

Common flags: `--ignore-user-config --ignore-rules --disable memories
--disable external_agent_memory_import --disable hooks --disable apps
--disable plugins -c approval_policy="never"`. The skill also sets
`-c model_reasoning_summary="detailed"` so run logs show Codex's reasoning
summaries.

| Profile | Model and effort | Sandbox and extras |
|---|---|---|
| Plan discussion | `gpt-6-astra`, `xhigh` | `-s read-only` |
| Implementation | `gpt-5.6-sol`, `high` | `-s workspace-write --add-dir ~/.cache/uv -c web_search="disabled"` |
| Independent review | `gpt-5.6-sol`, `high` | `-s read-only`, fresh session |

Resume by UUID, never `--last`, from the repository directory, applying all
common flags and the selected profile's model, effort, sandbox
(`-c sandbox_mode=...`), writable roots, and web setting again. `resume` uses the
current directory as its workspace, not the original session's. The skill holds the exact fresh and resume commands. If `uv run`
cannot use the shared cache, the verified fallback is `.venv/bin/python -m pytest`;
the report states which ran.

Canaried on 2026-09-22 (tool inventories are as reported by the model):

- workspace-write with `--ignore-rules` blocked `git add`, `git commit`, and
  shell network in a throwaway repository; without the flag, user-level Codex
  rules that pre-approve `git add` let it succeed;
- the common flags (before apps/plugins were added) with read-only blocked
  `git add --dry-run` and `touch` in the checkout and loaded `AGENTS.md`;
- the implementation profile's flags exposed no web tool;
- adding `--disable apps --disable plugins` removed `request_plugin_install`,
  the MCP resource tools, and the plugin-management skill; project skills
  remained;
- a resume under the common flags reported read-only and approval `never`, but
  kept app tools the session started with;
- `uv run pytest` passed with `~/.cache/uv` writable, via `codex sandbox`;
- the complete implementation profile (`gpt-5.6-sol`, `high`) blocked `git add`,
  `git commit`, network access, and writes outside the workspace, allowed
  writes to the uv cache, and exposed no web, app, or plugin tools; a resume
  under the same profile kept those restrictions;
- a fresh plan-discussion session (`gpt-6-astra`, `xhigh`) under the complete
  profile was read-only with approval `never` and exposed no plugin tools;
- in the NightCrate checkout, `uv run pytest` and `uv run ruff check` passed
  inside an implementation-profile `codex exec` run, and the before/after file
  inventory showed no changes;
- a resume launched from a different folder used that folder as its writable
  workspace and wrote a file there; Git writes stayed blocked.

The `codex` skill records how to re-run these checks.

## 11. Where things live

- This document holds the roles, gates, and records; `CLAUDE.md` links to it.
- The Claude-only skill `.claude/skills/codex/` holds the exact commands, prompt
  templates, and the file-inventory script.
- `start-version` runs the pending-outcome sweep. `finalize-session` separates
  *Prepare* (before Fred's acceptance test; no application refactoring) from
  *Publish* (after authorization, with the remote SHA check) and updates outcome
  states. `sync-docs` keeps `PLAN.md` lifecycle status accurate.
- Specs and plans live in `docs/superpowers/`; raw Codex exchanges live in the
  ignored `.superpowers/codex/<version>/`.
