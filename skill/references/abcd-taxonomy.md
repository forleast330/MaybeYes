# MaybeYes ABCD Taxonomy

MaybeYes classifies each action before deciding whether to proceed optimistically.

## A - Read-only / exploration

Likely auto:

- `ls`, `pwd`, `tree`;
- `find`, `rg`, `grep`;
- `git status`, `git diff`, `git log`, `git show`;
- reading normal source, test, documentation, and config files inside the workspace;
- command help or version checks;
- local test discovery that does not mutate state.

Do not treat as ordinary A:

- `.env`, `.env.*`;
- SSH keys, GPG keys, API tokens, cloud credentials;
- browser cookies, password stores, private certs;
- files outside the expected workspace;
- reading data for the purpose of sending it externally.

## B - Reversible local changes

Likely optimistic if rollback exists:

- edit source files directly related to the task;
- add or update tests;
- update docs;
- run formatters;
- update generated files if they can be regenerated;
- local refactors in a bounded path.

Guardrails:

- preserve original user changes;
- prefer draft worktree/patch queue/temporary branch;
- never overwrite uncommitted user work without inspection;
- log each file touched;
- provide rollback steps.

## C1 - Controlled external/persistent side effects

Possible optimistic with high threshold:

- install dependencies already declared in lockfile or manifest;
- read-only network calls to expected/trusted domains;
- push to the same non-protected feature branch;
- create a draft PR;
- write artifacts to a known dev-only location.

Required conditions:

- user intent covers the action;
- non-production context;
- scoped target;
- undoable or idempotent;
- high confidence.

## C2 - Treat as D

Examples:

- push to `main`, `master`, `release/*`, protected branches;
- create non-draft releases;
- publish packages;
- modify shared infra;
- change permissions, IAM, repo settings;
- send team-wide notifications;
- mutate remote databases or queues.

## D - Never auto-execute

Examples:

- `git push --force`;
- `git reset --hard`;
- `git clean -fd`;
- `git checkout -- .`;
- `git restore .`;
- deleting existing user files;
- `rm -rf` outside a clearly generated temp dir;
- production deploys;
- database migrations, `drop`, `truncate`;
- `terraform destroy`, destructive `terraform apply`, `pulumi destroy`, `cdk destroy`;
- cloud/IAM permission changes;
- reading or transmitting secrets;
- `curl ... | bash` or equivalent downloaded-code execution;
- package publishing;
- release signing;
- writing agent-control/protected config without explicit user intent.
