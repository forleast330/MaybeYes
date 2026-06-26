# MaybeYes Ledger Format

The ledger is the report in "proceed first, report later". No ledger, no MaybeYes.

## User-facing ledger

```markdown
## MaybeYes Ledger

### Auto-proceeded
| ID | Class | Action | Confidence | Scope | Rollback |
|---:|---|---|---:|---|---|
| 1 | A | `rg "PaymentClient" src tests` | high | read-only | n/a |
| 2 | B | Edited `src/payment/client.ts` | 0.82 | local patch | discard patch |

### Needs approval
| ID | Class | Action | Reason |
|---:|---|---|---|
| 3 | C1 | `git push origin fix-payment-timeout` | external side effect |

### Never auto-ran
| ID | Class | Action | Reason |
|---:|---|---|---|
| 4 | D | `git push --force` | force push |
```

## Machine-readable event schema

```json
{
  "id": 1,
  "timestamp": "2026-06-26T15:04:05+08:00",
  "session_id": "optional-host-session-id",
  "class": "B",
  "action_type": "file_edit",
  "canonical_action": "edit src/payment/client.ts",
  "raw_command_or_tool": "Edit(file_path=src/payment/client.ts)",
  "confidence": 0.82,
  "decision": "optimistic_execute",
  "scope": "workspace/local patch",
  "rollback": "discard patch hunk or restore file from git",
  "files_touched": ["src/payment/client.ts"],
  "network_domains": [],
  "risk_notes": ["local", "reversible", "inside task scope"],
  "host_policy_result": "allowed",
  "final_user_feedback": null
}
```

## Decision values

```text
execute_now
execute_in_draft
optimistic_execute
batch_ask
ask_now
deny
host_blocked
```

## Feedback labels

```text
explicit_approve
explicit_deny
implicit_accept
implicit_reject
approve_once
approve_always
approve_with_modification
```

Use explicit feedback as strong training data. Use implicit feedback with lower weight.
