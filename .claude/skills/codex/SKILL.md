---
name: codex
description: Claude-only. Run Codex for plan discussion, implementation handoffs, and independent review with the approved isolation profiles, prompt templates, and file inventory.
---

# Codex

Claude-only; `.agents/skills/` has no pointer for this skill. Read
[`docs/agent-collaboration.md`](../../../docs/agent-collaboration.md) first: it
defines the roles, gates, and records this skill carries out.

## Records

Use `.superpowers/codex/<version>/` (ignored) for every exchange, numbered in
order: `NN-claude-<step>.md` for what Claude sends, `NN-codex-<step>.log` for the
full run log, and `NN-codex-<step>.md` for Codex's final message. Record
`codex --version` in the first file of each version. Fred can follow a run with
`tail -f` on its log.

## Profiles

Define these in the shell before running; they match
[§10](../../../docs/agent-collaboration.md#10-command-profiles-codex-cli-01560).
Only Fred changes models or effort levels.

```bash
COMMON=(--ignore-user-config --ignore-rules --disable memories
  --disable external_agent_memory_import --disable hooks --disable apps
  --disable plugins -c 'approval_policy="never"'
  -c 'model_reasoning_summary="detailed"')
PLAN=(-m gpt-6-astra -c 'model_reasoning_effort="xhigh"' -s read-only)
IMPL=(-m gpt-5.6-sol -c 'model_reasoning_effort="high"' -s workspace-write
  --add-dir "$HOME/.cache/uv" -c 'web_search="disabled"')
REVIEW=(-m gpt-5.6-sol -c 'model_reasoning_effort="high"' -s read-only)
```

**Fresh session.** Put the full brief in a record file and pass a short pointer:

```bash
codex exec "${COMMON[@]}" "${PLAN[@]}" -C "$REPO" -o "$REC/02-codex-round1.md" \
  "Read $REC/01-claude-round1.md and do what it asks. Read-only." \
  > "$REC/02-codex-round1.log" 2>&1
```

Run it with `run_in_background`; the completion notice re-invokes Claude. Take
the session ID from the log's `session id:` header line.

**Resume** by ID, never `--last`, from the repository directory: `resume` takes
the shell's current directory as its workspace, whatever the original session
used (a canary resumed from another folder wrote there). It accepts no `-s`,
`-C`, or `--add-dir`, so `cd "$REPO"` first and restate the profile with `-c`:

```bash
# Plan discussion or review
codex exec resume "$SID" "${COMMON[@]}" -m gpt-6-astra \
  -c 'model_reasoning_effort="xhigh"' -c 'sandbox_mode="read-only"' -o ... "<prompt>"
# Implementation
codex exec resume "$SID" "${COMMON[@]}" -m gpt-5.6-sol \
  -c 'model_reasoning_effort="high"' -c 'sandbox_mode="workspace-write"' \
  -c "sandbox_workspace_write.writable_roots=[\"$HOME/.cache/uv\"]" \
  -c 'web_search="disabled"' -o ... "<prompt>"
```

A resumed session keeps the tools and context it started with, so every plan
discussion and independent review starts fresh under the complete profile.
Check each log header (model, sandbox, approval, effort) before using a result.

## Plan discussion

1. Snapshot the baseline spec and plan into the record folder; note the base SHA.
2. Round 1: [templates/plan-review.md](templates/plan-review.md), or
   [templates/blinded-prepass.md](templates/blinded-prepass.md) when the plan
   hinges on an open architectural or product choice.
3. Verify each finding against the code before answering. Answer all open
   points in one batched file per round. At most five rounds; more needs Fred.
4. Report to Fred with [templates/landing-report.md](templates/landing-report.md).
   Add the plan's Codex review section from
   [templates/plan-record.md](templates/plan-record.md).

## Implementation handoff

1. Provision dependencies first. Confirm no other writer is active.
2. `python3 .claude/skills/codex/scripts/inventory.py snapshot --root "$REPO" --out "$REC/NN-inventory-before.json"`
3. Send [templates/handoff.md](templates/handoff.md) with the `IMPL` profile.
4. Snapshot again (`...-after.json`) and run `inventory.py diff` on the pair.
   Every deletion or out-of-scope change is a finding. Compare with
   `git status` and `git diff`.
5. Review, re-run checks, stage, and batch findings back to the writer session
   as `docs/agent-collaboration.md` §4 describes.

## Independent review

Start a fresh session with `REVIEW` and
[templates/independent-review.md](templates/independent-review.md). Never reuse
the writer's session. Required for high-stakes work and for material
Claude-authored changes before Fred's acceptance test.

## Canaries

Re-run after any Codex CLI update (`codex --version` changes) or change to its
configuration or rules, and before trusting a profile that has not been checked:

```bash
.claude/skills/codex/scripts/canary.sh <empty-output-dir>
```

Read every report it writes. Expected: Git writes, network, and writes
outside the workspace blocked; uv cache writable in the implementation profile;
no web tool when disabled; no app or plugin tools; read-only where stated.
Record the result in `docs/agent-collaboration.md` §10.

## If Codex cannot run

Report the gap and its consequence to Fred. Continue only independent work
already authorized. Do not substitute another model or reviewer.
