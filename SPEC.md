# MaybeYes Design Specification

> **MaybeYes = predictive permissioning for coding agents.**
>
> A/B/C 类动作先斩后奏；D 类动作必须先问。

## 1. Purpose

MaybeYes is a skill/workflow for coding agents such as Codex and Claude Code. Its purpose is to reduce repetitive approval prompts while preserving explicit human control over dangerous actions.

The core user experience is:

```text
The agent estimates whether the user would approve an action.
If the action is A/B/C1 and safe enough, it proceeds first and logs the action.
If the action is D, or C is too broad, it asks before execution.
```

MaybeYes is intentionally not a permission bypass. It is a decision protocol layered on top of the host agent's permission system.

## 2. Non-goals

MaybeYes must not:

- bypass Codex sandboxing, Claude Code permissions, managed policy, OS sandboxing, or explicit ask/deny rules;
- auto-run production deploys, destructive infrastructure changes, force pushes, package publishing, hard resets, credential exfiltration, or broad deletion;
- silently mutate protected paths such as `.git`, `.codex`, `.agents`, `.claude`, `.github`, `.env`, SSH keys, or cloud credentials;
- treat user non-intervention as strong approval;
- learn unsafe behavior from biased implicit signals.

## 3. Target platforms

### 3.1 Codex

Codex supports Agent Skills as directories containing `SKILL.md`, optional scripts, optional references, and optional metadata. Repo-scoped Codex skills can live under `.agents/skills/<skill-name>/SKILL.md`.

Recommended MaybeYes install path:

```text
.agents/skills/maybeyes/SKILL.md
```

Optional metadata:

```text
.agents/skills/maybeyes/agents/openai.yaml
```

### 3.2 Claude Code

Claude Code supports skills as directories containing `SKILL.md`. Repo-scoped Claude skills can live under `.claude/skills/<skill-name>/SKILL.md`, and users can invoke them as `/<skill-name>`.

Recommended MaybeYes install path:

```text
.claude/skills/maybeyes/SKILL.md
```

### 3.3 Cross-agent compatibility

The shared implementation should use the Agent Skills open-standard subset:

```text
maybeyes/
├── SKILL.md
├── references/
│   ├── abcd-taxonomy.md
│   └── ledger-format.md
└── agents/
    └── openai.yaml    # Codex optional metadata
```

Do not rely on Claude-only frontmatter such as `allowed-tools` in the portable core skill unless you intentionally create a Claude-specific variant.

## 4. Risk taxonomy

### A — Read-only / exploration

Examples:

- `ls`, `pwd`, `find`, `rg`, `grep`;
- `git status`, `git diff`, `git log`;
- reading ordinary project files;
- inspecting package metadata;
- running help commands such as `npm test -- --help`.

Default behavior:

```text
execute now + log briefly
```

Exceptions:

- reading secrets, `.env`, SSH keys, cloud credentials, tokens, private certs, or password stores;
- reading files outside the task's expected workspace;
- reading files solely to send them to an external endpoint.

These exceptions become D or ask-now.

### B — Reversible local changes

Examples:

- editing source files within the task scope;
- adding tests;
- formatting files;
- editing local docs;
- updating generated local artifacts if reproducible.

Default behavior:

```text
if p_approve >= 0.50 and rollback exists: optimistic execute
else: batch ask
```

Required guardrails:

- operate in a git worktree, patch queue, draft branch, or clean working tree where rollback is simple;
- log files touched and diff summary;
- show the ledger before finalizing.

### C1 — Controlled external/persistent side effects

Examples:

- installing dependencies already listed in `package.json`, `pyproject.toml`, lockfiles, or equivalent manifests;
- read-only network fetches to trusted domains;
- pushing to the same feature branch the task is already using;
- creating a draft PR in the expected repo;
- uploading CI artifacts to a known development location.

Default behavior:

```text
if p_approve >= 0.85 and action is scoped, non-production, and undoable/idempotent: optimistic execute
else: batch ask
```

### C2 — Broad, shared, or hard-to-reverse side effects

Examples:

- pushing to `main`, `master`, release, or protected branches;
- modifying shared infrastructure;
- changing repository permissions;
- applying cloud/IAM/database changes;
- package publishing;
- sending messages to team channels;
- non-draft PR creation when policy requires review.

Default behavior:

```text
treat as D
```

### D — Dangerous / irreversible / sensitive

Examples:

- `git push --force`, `git reset --hard`, `git clean -fd`, `git checkout -- .`, `git restore .`;
- deleting existing user files or directories;
- production deploys and migrations;
- database `drop`, `truncate`, destructive migration, or irreversible schema changes;
- `terraform destroy`, destructive `terraform apply`, `pulumi destroy`, `cdk destroy`;
- cloud IAM changes, permission grants, credential rotation;
- reading or transmitting secrets;
- `curl ... | bash`, downloaded-code execution;
- package publishing such as `npm publish`, PyPI upload, release signing;
- writing to protected config or agent-control paths without explicit user intent.

Default behavior:

```text
never auto-execute; ask or deny
```

## 5. Decision algorithm

```python
def maybe_yes_decide(action, context):
    category = classify_by_hard_rules(action, context)

    if category == "D":
        return ask_user_or_deny(reason="D-class action")

    if violates_host_policy(action, context):
        return respect_host_policy()

    if category == "A":
        if touches_secret_or_protected_path(action):
            return ask_user_or_deny(reason="sensitive read")
        return execute_now(log=True)

    if category == "B":
        if not has_rollback_plan(action, context):
            return batch_ask(reason="no rollback plan")
        p = predict_approval(action, context)
        if p >= 0.50:
            return execute_in_draft_or_workspace(log=True, confidence=p)
        return batch_ask(confidence=p)

    if category == "C1":
        if touches_prod_or_shared_critical_resource(action, context):
            return ask_user_or_deny(reason="critical shared/prod resource")
        if not is_scoped_and_undoable_or_idempotent(action, context):
            return batch_ask(reason="C action not safely scoped")
        p = predict_approval(action, context)
        if p >= 0.85:
            return execute_now(log=True, confidence=p)
        return batch_ask(confidence=p)

    return batch_ask(reason="unknown category")
```

## 6. Prediction model

### 6.1 Initial heuristic model

Before collecting enough click data, use a deterministic heuristic:

| Signal | Effect |
|---|---|
| User explicitly requested the result | raises probability |
| Action is standard for the task | raises probability |
| Action is local and reversible | raises probability |
| Action touches many files | lowers probability |
| Action touches protected paths | force ask/D |
| Action reaches network | lowers probability unless expected |
| Action changes external state | requires C1 threshold or ask |
| Ambiguous user intent | lowers probability |

### 6.2 Learned model

A simple logistic regression model is sufficient for v1.

Suggested features:

```text
user_id_hash
repo_id_hash
action_category
command_family
canonical_command
file_globs_touched
path_sensitivity
num_files_touched
diff_lines_added
diff_lines_removed
network_used
network_domains
git_branch_type
is_protected_branch
has_destructive_flags
has_rollback_plan
is_prod_context
uses_secrets
user_prompt_contains_explicit_intent
previous_similar_approvals
previous_similar_denials
host_tool
session_phase
```

Suggested labels:

```text
explicit_approve
explicit_deny
implicit_accept
implicit_reject
approve_once
approve_always
approve_with_modification
```

Important: implicit signals must have lower training weight.

```text
explicit_approve: 1.0
explicit_deny: 1.0
implicit_accept: 0.3
implicit_reject: 0.8
```

This prevents a self-reinforcing loop where automatically executed actions are later counted as strong approval merely because the user did not notice or object.

### 6.3 Training cadence

Recommended rollout:

1. **Shadow mode:** predict and log but do not auto-execute beyond normal permissions.
2. **A/B mode:** enable optimistic execution for A and B only.
3. **C1 mode:** enable C1 only with high threshold and strict scoping.
4. **Suggestions:** propose new allow/ask rules based on repeated explicit approvals.

Daily retraining is fine for an individual user. For teams, retrain per user/team/repo and keep a global conservative prior.

## 7. Ledger schema

Every MaybeYes run maintains an append-only ledger for the session.

```json
{
  "id": 3,
  "timestamp": "2026-06-26T15:04:05+08:00",
  "class": "B",
  "action_type": "file_edit",
  "canonical_action": "edit src/payment/client.ts",
  "raw_command_or_tool": "Edit(file_path=src/payment/client.ts)",
  "confidence": 0.82,
  "decision": "optimistic_execute",
  "scope": "workspace/local patch",
  "rollback": "discard patch hunk or git checkout -- src/payment/client.ts",
  "files_touched": ["src/payment/client.ts"],
  "network_domains": [],
  "risk_notes": ["local", "reversible", "inside task scope"],
  "final_user_feedback": null
}
```

The user-facing ledger should be compact, but the machine ledger can be verbose.

## 8. Batch approval UX

When the agent hits a low-confidence C1 or any D action, it should present:

```markdown
## MaybeYes approval checkpoint

I already proceeded with these safe actions:

| ID | Class | Action | Why it was safe |
|---:|---|---|---|
| 1 | A | `rg "PaymentClient" src tests` | read-only |
| 2 | B | edited `src/payment/client.ts` | local reversible patch |

Now I need your approval for:

| ID | Class | Action | Reason |
|---:|---|---|---|
| 3 | C1 | `git push origin fix-payment-timeout` | external side effect |
| 4 | D | `git push --force` | force push; never auto-runs |

Reply with one of:
- approve 3
- approve all except 4
- deny 3 and continue locally
- stop and show full diff
```

## 9. Host integration notes

### Codex

Recommended default:

```toml
sandbox_mode = "workspace-write"
approval_policy = "on-request"
approvals_reviewer = "auto_review"

[sandbox_workspace_write]
network_access = false
```

MaybeYes should not instruct Codex to use `danger-full-access` or `approval_policy = "never"` except in explicitly isolated throwaway environments.

### Claude Code

Recommended default:

```json
{
  "permissions": {
    "defaultMode": "auto"
  }
}
```

Project or user settings can add allow/ask/deny rules. Deny and ask rules should be considered hard boundaries for MaybeYes.

For deterministic enforcement beyond skill instructions, implement Claude Code `PreToolUse` hooks that classify commands and force prompt/deny for D-class patterns.

## 10. Acceptance criteria for the v1 skill

A valid MaybeYes skill must:

- include `SKILL.md` with `name: maybeyes` and a clear `description`;
- define A/B/C1/C2/D categories;
- specify default thresholds for B and C1;
- state that host permissions/sandbox are never bypassed;
- require a ledger for optimistic actions;
- provide checkpoint phrasing for batch approval;
- include examples for Codex and Claude Code installation;
- keep the main `SKILL.md` concise and put details in `references/`.

## 11. References

- OpenAI Codex Agent Skills: https://developers.openai.com/codex/skills
- OpenAI Codex sandboxing: https://developers.openai.com/codex/concepts/sandboxing
- OpenAI Codex auto-review: https://developers.openai.com/codex/concepts/sandboxing/auto-review
- Claude Code skills: https://code.claude.com/docs/en/skills
- Claude Code permissions: https://code.claude.com/docs/en/permissions
- Claude Code auto mode: https://code.claude.com/docs/en/permission-modes
- Agent Skills open standard: https://agentskills.io/
