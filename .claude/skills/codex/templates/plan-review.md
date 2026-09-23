# Template — independent plan review (round 1)

From: Claude. To: Codex (plan-discussion profile, read-only). Round 1 of at most 5.

## Context
- Version and goal: <version — one sentence>
- Baseline: <spec path>, <plan path>, base SHA <sha>. Snapshots: <record paths>.
- Read `AGENTS.md`/`CLAUDE.md`, the spec, the plan, and these
  `docs/development-decisions.md` sections: <list>.
- Private notes to read: <none | named notes>. Do not read other notes.

## Fred-approved constraints
<list>. These change only by Fred's decision; still flag contradicting evidence
or risks.

## Facts
<decision-relevant claims, each labeled **verified** (how) or **assumed**; stable
context may share one provenance line. Absence claims cite the search.>

## What I need
1. Check the plan against the code. Cite `file:line` for every claim.
2. Findings as **blocker**, **major**, or **minor**, each with evidence and a
   proposed change.
3. Product opinions: does the plan serve a concrete imaging decision? What
   would you cut, add, or sequence differently?
4. Verification gaps: checks that would pass while proving nothing.
5. Anything you could not verify, labeled as such.

Read-only; modify nothing. Keep it under <N> words.
