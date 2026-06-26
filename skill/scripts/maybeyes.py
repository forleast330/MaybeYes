#!/usr/bin/env python3
"""MaybeYes runtime: classify, predict, ledger, and daily retrain.

Stdlib-only on purpose: skills should copy cleanly across agents.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


LABEL_WEIGHTS = {
    "explicit_approve": 1.0,
    "approve_once": 1.0,
    "approve_always": 1.0,
    "approve_with_modification": 0.6,
    "implicit_accept": 0.3,
    "implicit_reject": -0.8,
    "explicit_deny": -1.0,
}

PROTECTED_BRANCHES = {"main", "master", "develop", "release", "prod", "production"}
SECRET_PATTERNS = (
    ".env",
    "id_rsa",
    "id_ed25519",
    ".ssh/",
    "credentials",
    "token",
    "secret",
    "private_key",
    ".pem",
    ".p12",
)
D_PATTERNS = (
    r"git\s+push\b.*--force",
    r"git\s+reset\s+--hard",
    r"git\s+clean\s+-",
    r"git\s+checkout\s+--\s+\.",
    r"git\s+restore\s+\.",
    r"\brm\s+-rf\b",
    r"\bcurl\b.*\|\s*(ba)?sh\b",
    r"\bnpm\s+publish\b",
    r"\b(python|twine)\s+.*upload\b",
    r"\bterraform\s+destroy\b",
    r"\bterraform\s+apply\b.*(prod|production|destroy|delete)",
    r"\bpulumi\s+destroy\b",
    r"\bcdk\s+destroy\b",
    r"\biam\b|\bpermissions?\b",
    r"\bproduction\b.*\bdeploy\b|\bdeploy\b.*\bproduction\b",
    r"\bdatabase\b.*\bmigration\b|\bmigration\b.*\bdatabase\b",
    r"\b(drop|truncate)\s+(table|database)\b",
)
A_COMMANDS = ("ls", "pwd", "find", "rg", "grep", "git status", "git diff", "git log", "git show")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(min(x, 20), -20)))


class MaybeYesRuntime:
    def __init__(self, state_dir: Path | str):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.state_dir / "ledger.jsonl"
        self.feedback_path = self.state_dir / "feedback.jsonl"
        self.model_path = self.state_dir / "model.json"

    def decide(self, **context: Any) -> dict[str, Any]:
        self.maybe_retrain()
        klass, reason = self.classify(context)
        confidence = 0.0 if klass == "D" else self.predict(klass, context)
        decision = self.decision_for(klass, confidence, context)
        event = {
            "id": self.next_id(),
            "timestamp": now_iso(),
            "class": klass,
            "action_type": context.get("action_type", "command"),
            "canonical_action": context.get("action", ""),
            "confidence": round(confidence, 4),
            "decision": decision,
            "scope": self.scope_for(context),
            "rollback": context.get("rollback") or ("n/a" if klass == "A" else ""),
            "files_touched": context.get("files", []),
            "network_domains": context.get("network_domains", []),
            "risk_notes": [reason],
            "final_user_feedback": None,
            "features": self.features(klass, context),
        }
        self.append_jsonl(self.ledger_path, event)
        return event

    def classify(self, context: dict[str, Any]) -> tuple[str, str]:
        action = str(context.get("action", "")).lower()
        files = [str(path).lower() for path in context.get("files", [])]
        branch = str(context.get("branch", "")).lower()

        if context.get("production"):
            return "D", "production context"
        if self.touches_secret(files, action):
            return "D", "secret or credential access"
        if any(re.search(pattern, action) for pattern in D_PATTERNS):
            return "D", "D-class command pattern"
        if action.startswith("git push") and self.is_protected_branch(branch):
            return "D", "protected/shared branch push"
        if any(term in action for term in ("publish package", "release signing", "prod deploy")):
            return "D", "dangerous external side effect"

        if action.startswith("git push"):
            return "C1", "same feature branch push" if branch else "external side effect"
        if "install" in action and any(name in action for name in ("package", "dependency", "dependencies")):
            return "C1", "declared dependency install"
        if context.get("network_domains"):
            return "C1", "network side effect"

        if context.get("action_type") in {"file_edit", "format", "write"}:
            return "B", "reversible local change"

        if context.get("action_type") == "read" or any(action.startswith(cmd) for cmd in A_COMMANDS):
            return "A", "read-only exploration"

        return "B", "local task action"

    def decision_for(self, klass: str, confidence: float, context: dict[str, Any]) -> str:
        if klass == "D":
            return "ask_now"
        if klass == "A":
            return "execute_now"
        if klass == "B":
            if context.get("rollback") and confidence >= 0.50:
                return "optimistic_execute"
            return "batch_ask"
        if klass == "C1":
            safe = context.get("undoable") and not context.get("production") and not self.is_protected_branch(context.get("branch", ""))
            return "optimistic_execute" if safe and confidence >= 0.85 else "batch_ask"
        return "batch_ask"

    def predict(self, klass: str, context: dict[str, Any]) -> float:
        base = {"A": 0.97, "B": 0.62, "C1": 0.72}.get(klass, 0.35)
        if context.get("user_intent"):
            base += 0.12
        if context.get("rollback") or context.get("undoable"):
            base += 0.10
        if context.get("production") or context.get("network_domains"):
            base -= 0.20
        model = self.load_model()
        if model.get("weights"):
            score = sum(model["weights"].get(feature, 0.0) for feature in self.features(klass, context))
            base = (base + sigmoid(score)) / 2.0
        return max(0.0, min(base, 0.99))

    def maybe_retrain(self) -> None:
        model = self.load_model()
        trained_at = self.parse_time(model.get("trained_at"))
        if trained_at and datetime.now(timezone.utc) - trained_at < timedelta(hours=24):
            return
        if self.feedback_path.exists():
            self.train()

    def train(self) -> dict[str, Any]:
        weights: dict[str, float] = {}
        examples: list[tuple[list[str], int, float]] = []
        for item in self.read_jsonl(self.feedback_path):
            label_weight = LABEL_WEIGHTS.get(str(item.get("label")), 0.0)
            if label_weight == 0.0:
                continue
            label = 1 if label_weight > 0 else 0
            features = item.get("features") or self.features(str(item.get("class", "")), item)
            examples.append((features, label, abs(label_weight)))

        for _ in range(80):
            for features, label, sample_weight in examples:
                score = sum(weights.get(feature, 0.0) for feature in features)
                error = (label - sigmoid(score)) * sample_weight
                for feature in features:
                    weights[feature] = weights.get(feature, 0.0) + 0.08 * error

        model = {"trained_at": now_iso(), "examples": len(examples), "weights": weights}
        self.model_path.write_text(json.dumps(model, indent=2, sort_keys=True) + "\n")
        return model

    def add_feedback(self, event_id: int, label: str) -> dict[str, Any]:
        event = next((item for item in self.read_jsonl(self.ledger_path) if item.get("id") == event_id), None)
        if not event:
            raise SystemExit(f"event id not found: {event_id}")
        feedback = {
            "timestamp": now_iso(),
            "event_id": event_id,
            "label": label,
            "class": event.get("class"),
            "action_type": event.get("action_type"),
            "features": event.get("features", []),
        }
        self.append_jsonl(self.feedback_path, feedback)
        return feedback

    def features(self, klass: str, context: dict[str, Any]) -> list[str]:
        action = str(context.get("action", "")).lower()
        family = action.split(maxsplit=1)[0] if action else "unknown"
        features = [
            f"class:{klass}",
            f"action_type:{context.get('action_type', 'command')}",
            f"family:{family}",
        ]
        branch = context.get("branch")
        if branch:
            features.append("branch:protected" if self.is_protected_branch(branch) else "branch:feature")
        if context.get("rollback"):
            features.append("has_rollback")
        if context.get("undoable"):
            features.append("undoable")
        if context.get("user_intent"):
            features.append("explicit_intent")
        return features

    def touches_secret(self, files: list[str], action: str) -> bool:
        haystack = " ".join(files + [action])
        return any(pattern in haystack for pattern in SECRET_PATTERNS)

    def is_protected_branch(self, branch: str) -> bool:
        name = str(branch).lower().removeprefix("refs/heads/")
        return name in PROTECTED_BRANCHES or name.startswith("release/")

    def scope_for(self, context: dict[str, Any]) -> str:
        if context.get("production"):
            return "production"
        if context.get("branch"):
            return f"branch:{context['branch']}"
        if context.get("files"):
            return "workspace/local patch"
        return "workspace"

    def next_id(self) -> int:
        return sum(1 for _ in self.read_jsonl(self.ledger_path)) + 1

    def load_model(self) -> dict[str, Any]:
        if not self.model_path.exists():
            return {}
        return json.loads(self.model_path.read_text())

    def parse_time(self, value: str | None) -> datetime | None:
        if not value:
            return None
        return datetime.fromisoformat(value)

    def read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def append_jsonl(self, path: Path, item: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="MaybeYes prediction runtime")
    parser.add_argument("--state-dir", default=".maybeyes")
    sub = parser.add_subparsers(dest="command", required=True)

    decide = sub.add_parser("decide")
    decide.add_argument("action")
    decide.add_argument("--action-type", default="command")
    decide.add_argument("--file", action="append", default=[])
    decide.add_argument("--branch", default="")
    decide.add_argument("--user-intent", default="")
    decide.add_argument("--rollback", default="")
    decide.add_argument("--undoable", action="store_true")
    decide.add_argument("--production", action="store_true")
    decide.add_argument("--network-domain", action="append", default=[])

    feedback = sub.add_parser("feedback")
    feedback.add_argument("event_id", type=int)
    feedback.add_argument("label", choices=sorted(LABEL_WEIGHTS))

    sub.add_parser("train")

    args = parser.parse_args()
    runtime = MaybeYesRuntime(args.state_dir)
    if args.command == "decide":
        result = runtime.decide(
            action=args.action,
            action_type=args.action_type,
            files=args.file,
            branch=args.branch,
            user_intent=args.user_intent,
            rollback=args.rollback,
            undoable=args.undoable,
            production=args.production,
            network_domains=args.network_domain,
        )
    elif args.command == "feedback":
        result = runtime.add_feedback(args.event_id, args.label)
    else:
        result = runtime.train()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
