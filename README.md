# MaybeYes

> **先斩后奏 for coding agents.**
>
> A/B/C 类动作：大概率会批准，就先在安全边界内推进，并完整记账。  
> D 类动作：不猜，不赌，不先斩，必须先问。

**MaybeYes** is a cross-agent skill pattern for Codex and Claude Code. It reduces approval fatigue by letting the agent optimistically proceed on low- and medium-risk coding actions, while keeping irreversible or high-impact actions behind explicit user approval.

The name means exactly what the agent is thinking:

> “Maybe yes — the user probably wants this, so proceed safely, log it, and report it.”

## The rule

```text
ABC: Proceed first, report later.
D: Ask first, execute later.
Everything: Logged.
```

In Chinese:

```text
ABC 先斩后奏，D 类必须上奏。
```

This is **not** a permission-bypass tool. MaybeYes never overrides Codex sandbox rules, Claude Code permission rules, OS sandboxing, managed policies, or explicit deny/ask rules. It is an agent workflow: classify, predict, act only when safe enough, and show a ledger.

## Why this exists

Coding agents often stop for approvals that users almost always grant: search files, run tests, edit source files, format code, or create local tests. Repeated approvals break flow.

MaybeYes changes the UX from:

```text
Can I run grep?
Can I edit this file?
Can I run tests?
Can I edit another file?
Can I run tests again?
```

to:

```text
I proceeded with safe A/B actions.
Here is the ledger.
Now I need approval for this C/D action.
```

The goal is speed without pretending all actions are equally safe.

## Risk categories

| Class | Meaning | Examples | Default MaybeYes behavior |
|---|---|---|---|
| **A** | Read-only / exploration | `ls`, `grep`, `rg`, `git diff`, reading normal project files, `npm test -- --help` | Execute automatically and log briefly. |
| **B** | Reversible local changes | Editing `src/**`, `tests/**`, docs, formatting, adding local tests | Optimistically execute if confidence is above threshold; prefer draft worktree, patch queue, or clean git rollback. |
| **C1** | Controlled external or persistent side effect | Installing dependencies already declared in lockfile/manifest, pushing to the same feature branch, creating a draft PR | Execute only with higher confidence and narrow scope; otherwise batch ask. |
| **C2** | Shared or hard-to-reverse side effect | Pushing to shared branch, publishing packages, applying cloud changes, modifying shared infra | Treat as D. |
| **D** | Dangerous / irreversible / sensitive | `git push --force`, `git reset --hard`, deleting existing user files, production deploys, DB migrations, IAM changes, secrets exfiltration, `curl \| bash` | Never auto-execute. Ask first or deny. |

## Thresholds

MaybeYes includes a stdlib Python runtime at [`skill/scripts/maybeyes.py`](./skill/scripts/maybeyes.py). It combines hard-rule classification, heuristic approval scoring, a lightweight learned model, JSONL feedback, ledger logging, and automatic retraining when the saved model is older than 24 hours.

Recommended default thresholds:

```text
A: execute unless it touches secrets or protected paths
B: p_approve >= 0.50, only if reversible/local
C1: p_approve >= 0.85, only if non-production, scoped, and undoable/idempotent
D: never auto-execute
```

If no model exists, use confidence labels instead of fake precision:

```text
high    ~= user explicitly asked for this and it is inside scope
medium  ~= likely useful but not explicitly requested
low     ~= side effect, broad scope, or ambiguous intent
blocked ~= D-class or policy-forbidden
```

Runtime example:

```bash
python3 skill/scripts/maybeyes.py --state-dir .maybeyes decide \
  "git push origin feature/foo" \
  --branch feature/foo \
  --user-intent "push current feature branch" \
  --undoable
```

Record feedback and let the next decision retrain if 24 hours have passed:

```bash
python3 skill/scripts/maybeyes.py --state-dir .maybeyes feedback 1 explicit_approve
```

## The ledger

Every optimistic action must be recorded.

Example:

```markdown
## MaybeYes Ledger

### Auto-proceeded
| ID | Class | Action | Confidence | Scope | Rollback |
|---:|---|---|---:|---|---|
| 1 | A | `rg "PaymentClient" src tests` | 0.97 | read-only | n/a |
| 2 | B | Edited `src/payment/client.ts` | 0.82 | local patch | discard patch |
| 3 | B | Added `tests/payment-client.test.ts` | 0.78 | local patch | discard patch |

### Needs approval
| ID | Class | Action | Why |
|---:|---|---|---|
| 4 | C1 | `git push origin fix-payment-timeout` | external side effect; confidence below C1 threshold |

### Never auto-ran
| ID | Class | Action | Reason |
|---:|---|---|---|
| 5 | D | `git push --force` | force push |
```

The ledger is shown:

1. whenever the user asks what happened;
2. before asking for C/D approval;
3. at the end of the task;
4. before applying draft changes to the real workspace.

## Install as a Codex skill

Codex skills are Agent Skills directories containing a `SKILL.md`. For a repo-local install:

```bash
mkdir -p .agents/skills/maybeyes
cp -R skill/* .agents/skills/maybeyes/
```

Then invoke explicitly in Codex with:

```text
$maybeyes
```

or let Codex auto-select it when the task matches the description.

Optional Codex config example:

```toml
# ~/.codex/config.toml
sandbox_mode = "workspace-write"
approval_policy = "on-request"
approvals_reviewer = "auto_review"

[sandbox_workspace_write]
network_access = false
```

## Install as a Claude Code skill

Claude Code skills also use `SKILL.md`. For a repo-local install:

```bash
mkdir -p .claude/skills/maybeyes
cp -R skill/* .claude/skills/maybeyes/
```

Then invoke explicitly with:

```text
/maybeyes
```

Optional Claude Code settings example:

```json
{
  "permissions": {
    "defaultMode": "auto",
    "allow": [
      "Bash(rg *)",
      "Bash(grep *)",
      "Bash(git diff *)",
      "Bash(npm test)",
      "Bash(npm run test)",
      "Bash(npm run lint)",
      "Bash(pnpm test)",
      "Bash(pnpm run lint)"
    ],
    "ask": [
      "Bash(git push *)",
      "Bash(npm publish *)",
      "Bash(terraform apply *)",
      "Bash(kubectl apply *)"
    ],
    "deny": [
      "Bash(curl * | bash *)",
      "Bash(git push --force *)",
      "Bash(rm -rf / *)",
      "Read(./.env)",
      "Read(./.env.*)",
      "Read(./id_rsa)"
    ]
  }
}
```

## Suggested usage prompt

```text
Use MaybeYes for this task.
For A/B/C1 actions, proceed first when safe and reversible, then show the MaybeYes Ledger.
For D actions, stop and ask.
Do not bypass host permissions, sandboxing, explicit ask rules, or deny rules.
```

## What to give Codex to implement

This repository includes:

- [`SPEC.md`](./SPEC.md): the product/design specification.
- [`SPEC.zh-CN.md`](./SPEC.zh-CN.md): 中文方案文档，可直接发给 Codex/Claude Code 做二次实现。
- [`PROMPT_FOR_CODEX.md`](./PROMPT_FOR_CODEX.md): a ready-to-paste implementation prompt.
- [`skill/SKILL.md`](./skill/SKILL.md): a draft cross-agent MaybeYes skill.
- [`skill/scripts/maybeyes.py`](./skill/scripts/maybeyes.py): runtime classifier, predictor, ledger, feedback, and 24-hour retrainer.
- [`skill/references/`](./skill/references/): taxonomy and ledger details.
- [`examples/`](./examples/): example Codex and Claude Code settings.

## Safety invariants

MaybeYes must always preserve these invariants:

1. **Host policy is the ceiling.** If Codex or Claude Code asks, blocks, or denies, MaybeYes respects it.
2. **D is never predicted.** D-class actions must be manually approved or rejected.
3. **Secrets are special.** Reading or transmitting credentials is never an ordinary A action.
4. **B needs rollback.** Local edits should be patchable, reversible, or isolated.
5. **C needs scope.** C1 must be non-production, narrow, and undoable/idempotent.
6. **The ledger is mandatory.** “先斩后奏” only works if the “奏” is clear, complete, and reviewable.

## References

- OpenAI Codex Agent Skills: https://developers.openai.com/codex/skills
- OpenAI Codex sandboxing and approvals: https://developers.openai.com/codex/concepts/sandboxing
- OpenAI Codex auto-review: https://developers.openai.com/codex/concepts/sandboxing/auto-review
- Claude Code skills: https://code.claude.com/docs/en/skills
- Claude Code permissions: https://code.claude.com/docs/en/permissions
- Claude Code auto mode: https://code.claude.com/docs/en/permission-modes
- Agent Skills open standard: https://agentskills.io/

## License

MIT. See [`LICENSE`](./LICENSE).
