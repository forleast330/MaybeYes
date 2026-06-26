# MaybeYes 中文方案文档

> **MaybeYes：给 Coding Agent 用的“预测式审批”方案。**
>
> 核心口号：**ABC 先斩后奏，D 类必须上奏。**

## 1. 背景

Codex、Claude Code 这类 coding agent 很容易频繁请求批准：读文件要问，改文件要问，跑测试要问，装依赖要问，push 也要问。很多批准其实用户几乎都会点同意，于是审批本身变成了主要摩擦。

MaybeYes 的目标不是取消权限系统，而是把审批 UX 改成：

```text
低风险/中风险动作：agent 先按用户大概率意图推进，并把每一步记账。
高风险动作：agent 停下来问。
```

也就是说：

```text
A/B/C1：先斩后奏
D：必须先奏后斩
```

MaybeYes 是一个 **skill/workflow**，不是越权工具。它不能绕过 Codex sandbox、Claude Code permission rules、managed settings、OS sandbox、ask/deny rules 或任何宿主工具的拦截。

## 2. 总体原则

MaybeYes 每次准备执行动作前，都先做三件事：

```text
1. 分类：这个动作是 A、B、C1、C2 还是 D？
2. 预测：如果是 A/B/C1，用户大概率会不会批准？
3. 记账：如果先执行，必须写入 MaybeYes Ledger。
```

最终决策：

| 类别 | 是否允许预测批准 | 是否允许先执行 | 规则 |
|---|---:|---:|---|
| A | 是 | 是 | 普通只读探索自动执行；敏感读取例外。 |
| B | 是 | 是 | 可撤销本地修改可以先做，最好在 worktree/patch/draft 中。 |
| C1 | 是 | 有条件 | 必须非生产、窄范围、可撤销或幂等，并且置信度高。 |
| C2 | 否 | 否 | 视为 D。 |
| D | 否 | 否 | 永远人工批准或拒绝。 |

## 3. A/B/C/D 分类

### A：只读 / 探索

例子：

```text
ls
pwd
rg / grep / find
git status
git diff
git log
读取普通 source/test/docs 文件
查看命令 --help / --version
```

默认行为：

```text
自动执行 + 简短记账
```

例外：

```text
.env
.env.*
SSH key
API token
cloud credentials
password store
private cert
读取文件后准备外传
```

这些不是普通 A 类，应该进入 D 或 ask-now。

### B：可撤销本地修改

例子：

```text
修改 src/**
修改 tests/**
新增测试
修改 docs
格式化代码
本地小型重构
```

默认行为：

```text
如果 p_approve >= 0.50 且有 rollback，就先执行。
否则批量询问。
```

B 类必须满足：

```text
在任务范围内
不覆盖用户未保存/未提交的重要修改
可通过 git/worktree/patch 丢弃或回滚
记录 touched files 和 rollback 方式
```

### C1：可控外部副作用 / 持久副作用

例子：

```text
安装 lockfile/manifest 中已有依赖
对可信域名做只读网络请求
push 到当前 feature branch
创建 draft PR
上传 dev-only artifact
```

默认行为：

```text
如果 p_approve >= 0.85，且非生产、窄范围、可撤销/幂等，就先执行。
否则批量询问。
```

### C2：共享、宽范围、难撤销副作用

例子：

```text
push 到 main/master/release/protected branch
发布 npm/PyPI package
创建正式 release
修改 cloud/IAM/repo permissions
修改 shared infrastructure
发团队通知
修改远程数据库或队列
```

默认行为：

```text
视为 D。
```

### D：危险 / 不可逆 / 敏感

例子：

```text
git push --force
git reset --hard
git clean -fd
git checkout -- .
git restore .
删除已有用户文件
生产部署
数据库 migration / drop / truncate
terraform destroy
破坏性 terraform apply
pulumi destroy / cdk destroy
cloud IAM 权限变更
读取或发送 secrets
curl ... | bash
npm publish / PyPI upload
release signing
```

默认行为：

```text
永远不自动执行。必须询问用户，或者直接拒绝。
```

## 4. 阈值设计

不要给所有类别统一 `0.5`。

推荐：

```text
A：普通只读自动执行；敏感读取除外
B：p_approve >= 0.50 且可撤销
C1：p_approve >= 0.85 且非生产、窄范围、可撤销/幂等
D：永远不预测批准
```

原因：

```text
B 类错了，多数可以丢弃 patch。
C 类错了，可能已经影响外部系统，所以阈值更高。
D 类错了，损失可能极大，所以不允许预测。
```

## 5. 决策伪代码

```python
def decide(action, context):
    category = hard_rule_classify(action, context)

    # 宿主工具权限是上限
    if host_policy_blocks_or_prompts(action):
        return respect_host_policy()

    # D 永远不自动执行
    if category == "D":
        return ask_user_or_deny(reason="D-class action")

    # A 默认自动，但 secrets/protected path 例外
    if category == "A":
        if touches_secret_or_protected_path(action):
            return ask_user_or_deny(reason="sensitive read")
        return execute_now(log=True)

    # B 可预测批准，但必须可撤销
    if category == "B":
        if not has_rollback(action, context):
            return batch_ask(reason="no rollback")
        p = approval_model_or_heuristic(action, context)
        if p >= 0.50:
            return execute_in_draft_or_workspace(log=True, confidence=p)
        return batch_ask(confidence=p)

    # C1 必须高置信度 + 窄范围 + 非生产 + 可撤销/幂等
    if category == "C1":
        if touches_prod_or_shared_critical_resource(action):
            return ask_user_or_deny(reason="prod/shared critical resource")
        if not scoped_and_undoable_or_idempotent(action):
            return batch_ask(reason="not safely scoped")
        p = approval_model_or_heuristic(action, context)
        if p >= 0.85:
            return execute_now(log=True, confidence=p)
        return batch_ask(confidence=p)

    # C2 和未知类别保守处理
    return ask_user_or_deny(reason="unknown or C2")
```

## 6. MaybeYes Ledger

MaybeYes 的“先斩后奏”必须有“奏”。所以 ledger 是强制的。

用户可见格式：

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

展示时机：

```text
用户问发生了什么时
遇到 C/D 需要审批时
任务结束时
把 draft patch 应用到真实工作区前
```

## 7. 批量审批 UX

不要每个命令都问一次。遇到需要问时，展示：

```markdown
## MaybeYes approval checkpoint

我已经先斩后奏执行了这些安全动作：

| ID | Class | Action | Why |
|---:|---|---|---|
| 1 | A | `git diff` | read-only |
| 2 | B | edited `tests/foo.test.ts` | reversible local patch |

现在需要你批准：

| ID | Class | Action | Reason |
|---:|---|---|---|
| 3 | C1 | `git push origin feature/foo` | external side effect |
| 4 | D | `git push --force` | D-class, never auto-runs |

请按 ID 批准或拒绝。
```

## 8. 点击率学习模型

可以记录用户每次点击作为样本，并每天训练一个 LR/logistic regression 模型。

建议特征：

```text
user_id_hash
repo_id_hash
action_category
command_family
canonical_command
file_globs_touched
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

标签：

```text
explicit_approve
explicit_deny
implicit_accept
implicit_reject
approve_once
approve_always
approve_with_modification
```

训练权重建议：

```text
explicit_approve: 1.0
explicit_deny: 1.0
implicit_accept: 0.3
implicit_reject: 0.8
```

原因：自动执行后用户没反对，不等于强批准。否则模型会自我强化，越来越大胆。

## 9. Codex 集成建议

安装路径：

```text
.agents/skills/maybeyes/SKILL.md
```

推荐配置：

```toml
sandbox_mode = "workspace-write"
approval_policy = "on-request"
approvals_reviewer = "auto_review"

[sandbox_workspace_write]
network_access = false
```

不要把 MaybeYes 的默认方案设计成 `danger-full-access` 或 `approval_policy = "never"`。如果用户要这样做，也应该只在一次性容器/VM/throwaway repo 里使用。

## 10. Claude Code 集成建议

安装路径：

```text
.claude/skills/maybeyes/SKILL.md
```

调用方式：

```text
/maybeyes
```

推荐与 Claude Code `auto` mode、`allow`、`ask`、`deny` 规则搭配。

例如：

```json
{
  "permissions": {
    "defaultMode": "auto",
    "ask": [
      "Bash(git push *)",
      "Bash(npm publish *)",
      "Bash(terraform apply *)"
    ],
    "deny": [
      "Bash(curl * | bash *)",
      "Bash(git push --force *)",
      "Read(./.env)"
    ]
  }
}
```

如果要做更强的确定性拦截，可以加 Claude Code `PreToolUse` hook，让 hook 对 D 类命令强制 ask/deny。Skill 负责行为规范，hook 负责硬执行。

## 11. v1 验收标准

MaybeYes v1 至少要做到：

```text
1. 有 SKILL.md，名称为 maybeyes。
2. 明确 ABCD 分类。
3. 明确 ABC 先斩后奏，D 必须上奏。
4. 明确不绕过宿主权限、sandbox、ask/deny rules。
5. B 类要求 rollback。
6. C1 类要求高阈值、窄范围、非生产、可撤销/幂等。
7. 每次乐观执行都进入 ledger。
8. 遇到 C/D 用 batch approval checkpoint，而不是单条命令反复问。
9. 能同时放进 Codex `.agents/skills/` 和 Claude Code `.claude/skills/`。
```

## 12. 一句话总结

```text
MaybeYes 不是“别问了直接干”。
MaybeYes 是“该干的先干，干了要记账；危险的别猜，必须先问”。
```
