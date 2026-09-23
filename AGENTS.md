# AGENTS.md

Read [CLAUDE.md](CLAUDE.md): it is the shared project guidance for every agent.
Keep instructions there rather than maintaining a second copy here.

- Use the running agent's identity for commit/PR attribution and verification
  checkmarks; never copy another model's example attribution.
- Harness-specific home-directory paths mean this agent's equivalent memory or
  configuration location.
- Project skills live in `.claude/skills/`. `.agents/skills/` contains pointers;
  edit the source skills and leave those pointers alone.

Fix shared guidance at its source. Add an exception here only when an actual
agent-specific difference requires one.
