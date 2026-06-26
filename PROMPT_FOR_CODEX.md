# Prompt for Codex

Use this prompt to ask Codex to implement or refine the MaybeYes skill.

```text
You are implementing MaybeYes, a cross-agent Agent Skill for Codex and Claude Code.

Read README.md and SPEC.md first.

Goal:
Create a portable skill named `maybeyes` that implements predictive permissioning for coding agents:
- A/B/C1 actions may proceed optimistically when safe enough, reversible/scoped, and logged.
- D actions must never auto-execute; they must be explicitly approved or denied.
- The skill must emphasize “先斩后奏” for A/B/C and “D 必须上奏” for dangerous actions.
- The skill must not bypass host permissions, sandboxing, explicit ask/deny rules, managed settings, or OS restrictions.

Deliverables:
1. `skill/SKILL.md` using Agent Skills frontmatter with:
   - name: maybeyes
   - description: concise trigger description for approval fatigue, predictive permissions, optimistic execution, ABCD risk classification, and approval ledgers
2. `skill/references/abcd-taxonomy.md`
3. `skill/references/ledger-format.md`
4. `skill/scripts/maybeyes.py` implementing classifier, predictor, ledger, feedback capture, and retraining when the model is older than 24 hours
5. `skill/agents/openai.yaml` for Codex optional metadata
6. `examples/codex/config.toml`
7. `examples/claude/settings.json`
8. Update README.md if needed.

Requirements:
- Keep `SKILL.md` concise and operational.
- Use imperative instructions.
- Include a ledger template.
- Include batch-approval checkpoint phrasing.
- Do not add scripts unless they are deterministic helpers and do not require external dependencies.
- Runtime scripts must use the standard library only.
- Do not recommend full-access or bypass mode as default.
- Treat secrets, production, protected branches, destructive commands, package publishing, IAM/cloud/DB mutations, and force push as D.
- B class requires rollback or draft isolation.
- C1 requires high confidence, narrow scope, non-production context, and undoable/idempotent behavior.

Acceptance tests:
- If asked to search and edit source/tests, the skill says to proceed and log.
- If asked to run `git push --force`, the skill says to ask first.
- If asked to read `.env`, the skill does not treat it as ordinary read-only A.
- If asked to deploy production or run database migrations, the skill asks first.
- If asked to push to current feature branch, the skill treats it as C1 and requires high confidence/scope checks.
```
