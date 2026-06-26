<p align="center">
  <img src="assets/maybeyes-logo.png" alt="MaybeYes logo" width="220">
</p>

<h1 align="center">MaybeYes</h1>

<p align="center">
  <strong>Predictive permissioning for coding agents.</strong>
</p>

<p align="center">
  <a href="./SPEC.md">Spec</a> | <a href="./skill/SKILL.md">Skill</a> | <a href="./tests/test_maybeyes_runtime.py">Tests</a> | <a href="./LICENSE">MIT</a>
</p>

MaybeYes is a portable Agent Skill for Codex and Claude Code. It reduces approval fatigue by letting an agent predict low-risk approvals, proceed inside clear safety boundaries, and keep a reviewable ledger. Dangerous, irreversible, or sensitive actions still require explicit approval.

```text
A/B/C1: proceed first when safe, scoped, and logged.
C2/D: ask first.
Everything: respect host permissions.
```

MaybeYes is not a permission bypass. It never overrides Codex sandboxing, Claude Code permissions, OS sandboxing, managed policies, explicit ask rules, or deny rules.

## Why It Exists

Coding agents often pause for approvals that users almost always grant: search files, inspect diffs, edit local source, add tests, format code, or run checks. Those prompts interrupt the work more than they protect it.

MaybeYes changes the flow from repeated single-action prompts to a ledger-first workflow:

```text
I proceeded with safe local actions.
Here is the ledger.
Now I need approval for this external or dangerous action.
```

## Runtime

The stdlib-only runtime lives at [`skill/scripts/maybeyes.py`](./skill/scripts/maybeyes.py). It includes:

- hard-rule A/B/C/D classification;
- heuristic approval scoring;
- an optional lightweight learned model;
- JSONL feedback and ledger events;
- automatic retraining when the saved model is missing or older than 24 hours.

Example:

```bash
python3 skill/scripts/maybeyes.py --state-dir .maybeyes decide \
  "git push origin feature/foo" \
  --branch feature/foo \
  --user-intent "push current feature branch" \
  --undoable
```

Record feedback:

```bash
python3 skill/scripts/maybeyes.py --state-dir .maybeyes feedback 1 explicit_approve
```

## Risk Model

| Class | Meaning | Examples | Default behavior |
|---|---|---|---|
| A | Read-only exploration | `rg`, `ls`, `git diff`, reading ordinary project files | Execute and log. |
| B | Reversible local changes | Edit source, add tests, format docs | Execute if likely approved and rollback exists. |
| C1 | Scoped external or persistent side effect | Install declared dependencies, push current feature branch, create draft PR | Execute only with high confidence, narrow scope, and undo/idempotency. |
| C2 | Broad or hard-to-reverse side effect | Push shared branch, publish package, mutate shared infra | Treat as D. |
| D | Dangerous, irreversible, or sensitive | Force push, hard reset, delete user files, production deploy, DB migration, secrets, downloaded-code execution | Ask first or deny. |

Recommended thresholds:

```text
A: execute unless it touches secrets or protected paths
B: p_approve >= 0.50, only if reversible/local
C1: p_approve >= 0.85, only if non-production, scoped, and undoable/idempotent
D: never auto-execute
```

## Ledger

Every optimistic action must be recorded.

```markdown
## MaybeYes Ledger

### Auto-proceeded
| ID | Class | Action | Confidence | Scope | Rollback |
|---:|---|---|---:|---|---|
| 1 | A | `rg "PaymentClient" src tests` | 0.97 | read-only | n/a |
| 2 | B | Edited `src/payment/client.ts` | 0.82 | local patch | discard patch |

### Needs approval
| ID | Class | Action | Why |
|---:|---|---|---|
| 3 | C1 | `git push origin fix-payment-timeout` | external side effect; below threshold |

### Never auto-ran
| ID | Class | Action | Reason |
|---:|---|---|---|
| 4 | D | `git push --force` | force push |
```

Show the ledger when the user asks what happened, before C/D approval checkpoints, and at task completion.

## Install

Codex:

```bash
mkdir -p .agents/skills/maybeyes
cp -R skill/* .agents/skills/maybeyes/
```

Claude Code:

```bash
mkdir -p .claude/skills/maybeyes
cp -R skill/* .claude/skills/maybeyes/
```

Invoke it explicitly with `$maybeyes` in Codex or `/maybeyes` in Claude Code.

## Repository Layout

```text
.
|-- assets/
|   `-- maybeyes-logo.png
|-- examples/
|   |-- claude/settings.json
|   `-- codex/config.toml
|-- skill/
|   |-- SKILL.md
|   |-- agents/openai.yaml
|   |-- references/
|   `-- scripts/maybeyes.py
|-- tests/
|   `-- test_maybeyes_runtime.py
|-- PROMPT_FOR_CODEX.md
`-- SPEC.md
```

## Test

```bash
python3 -B -m unittest tests/test_maybeyes_runtime.py
```

## Safety Invariants

1. Host policy is the ceiling.
2. D-class actions are never predicted into approval.
3. Secrets are never ordinary read-only actions.
4. Local edits need rollback.
5. C1 actions need high confidence, narrow scope, non-production context, and undo/idempotency.
6. The ledger is mandatory.

## License

MIT. See [`LICENSE`](./LICENSE).
