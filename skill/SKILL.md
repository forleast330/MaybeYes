---
name: maybeyes
description: Use MaybeYes for coding-agent approval fatigue, predictive permissions, optimistic execution, ABCD risk classification, approval ledgers, and “proceed first, report later” workflows. For A/B/C1 actions, proceed when safe, scoped, and reversible; for D actions, ask before executing.
---

# MaybeYes

**Core motto:** ABC 先斩后奏，D 类必须上奏.

Use this skill when the user wants fewer approval prompts, predictive permissioning, batched approvals, or a clear policy for when a coding agent should proceed versus ask.

## Non-negotiable boundaries

- Never bypass host permissions, sandboxing, managed policies, explicit ask rules, explicit deny rules, or OS restrictions.
- If Codex, Claude Code, a hook, a sandbox, or a permission rule blocks/prompts, respect that boundary.
- Never auto-execute D-class actions.
- Treat secrets and credential movement as sensitive even if the operation looks read-only.
- Keep a MaybeYes Ledger for every optimistic action.

## Classify every action before acting

### A — Read-only / exploration

Examples: `ls`, `pwd`, `rg`, `grep`, `git status`, `git diff`, reading ordinary project files, command help output.

Default: execute automatically and log briefly.

Exceptions: reading `.env`, tokens, SSH keys, cloud credentials, password stores, private certs, or files outside the expected workspace. Sensitive reads are not ordinary A actions; ask or deny.

### B — Reversible local changes

Examples: editing `src/**`, `tests/**`, docs, local config inside task scope, formatting, adding tests.

Default: optimistically execute when likely approved and rollback exists. Prefer draft worktree, patch queue, temporary branch, or clean git rollback. Log touched files and rollback method.

Default threshold: `p_approve >= 0.50`.

### C1 — Controlled external or persistent side effects

Examples: installing dependencies already declared in lockfiles/manifests, read-only network fetches to trusted domains, pushing to the same feature branch, creating a draft PR.

Default: execute only if all are true:

1. the user intent covers it;
2. confidence is high;
3. scope is narrow;
4. context is non-production;
5. the action is undoable or idempotent.

Default threshold: `p_approve >= 0.85`.

### C2 — Broad or hard-to-reverse side effects

Examples: pushing to `main`/`master`/release/protected branches, changing shared infrastructure, publishing packages, non-draft releases, team-wide messages, cloud resource mutation.

Default: treat as D.

### D — Dangerous / irreversible / sensitive

Examples: `git push --force`, `git reset --hard`, `git clean -fd`, deletion of pre-existing user files, production deploys, DB migrations, destructive cloud/IAM changes, package publishing, reading/transmitting secrets, downloaded-code execution such as `curl ... | bash`.

Default: never auto-execute. Ask for explicit approval or deny.

For more detail, read `references/abcd-taxonomy.md`.

## Approval prediction

If a real model exists, use it only for A/B/C1. Never use predicted approval to downgrade D.

If no model exists, use this heuristic:

- High confidence: user explicitly asked for the result and the action is standard, local, and reversible.
- Medium confidence: action is useful but not explicitly requested, or touches multiple files.
- Low confidence: action has external side effects, unclear scope, or ambiguous user intent.
- Blocked: D-class, secret-touching, production, destructive, or host-policy-denied action.

## Decision policy

```text
A: execute unless sensitive/protected.
B: execute optimistically if likely approved and rollback exists; otherwise batch ask.
C1: execute only with high confidence, narrow non-production scope, and undo/idempotency; otherwise batch ask.
C2: treat as D.
D: ask first or deny. Never auto-execute.
```

## Runtime predictor

Use `scripts/maybeyes.py` when deterministic classification, prediction, ledger logging, feedback capture, or retraining is needed.

Before an action, run:

```bash
python3 scripts/maybeyes.py --state-dir .maybeyes decide "git push origin feature/foo" --branch feature/foo --user-intent "push current feature branch" --undoable
```

The runtime returns JSON with `class`, `decision`, `confidence`, and ledger fields. It automatically retrains from `.maybeyes/feedback.jsonl` when `.maybeyes/model.json` is missing or older than 24 hours.

After user feedback, record it:

```bash
python3 scripts/maybeyes.py --state-dir .maybeyes feedback 1 explicit_approve
```

## MaybeYes Ledger

Maintain a ledger during the task. Show it when the user asks, before a C/D approval checkpoint, and at task completion.

Use this compact format:

```markdown
## MaybeYes Ledger

### Auto-proceeded
| ID | Class | Action | Confidence | Scope | Rollback |
|---:|---|---|---:|---|---|
| 1 | A | `rg "PaymentClient" src tests` | high | read-only | n/a |
| 2 | B | Edited `src/payment/client.ts` | medium-high | local patch | discard patch |

### Needs approval
| ID | Class | Action | Reason |
|---:|---|---|---|
| 3 | C1 | `git push origin fix-payment-timeout` | external side effect |

### Never auto-ran
| ID | Class | Action | Reason |
|---:|---|---|---|
| 4 | D | `git push --force` | force push |
```

For complete schema, read `references/ledger-format.md`.

## Batch approval checkpoint

When you must ask, ask in batches and include the prior optimistic actions.

Use this pattern:

```markdown
## MaybeYes approval checkpoint

I already proceeded with these safe actions:

| ID | Class | Action | Why |
|---:|---|---|---|
| 1 | A | `git diff` | read-only |
| 2 | B | edited `tests/foo.test.ts` | reversible local patch |

Now I need approval for:

| ID | Class | Action | Reason |
|---:|---|---|---|
| 3 | C1 | `git push origin feature/foo` | external side effect |
| 4 | D | `git push --force` | D-class, never auto-runs |

Please approve/deny by ID.
```

## End-of-task behavior

Before final response, summarize:

1. what was auto-proceeded;
2. what was not executed because it required approval;
3. what changed in the workspace;
4. how to rollback if relevant;
5. what tests/checks ran.
