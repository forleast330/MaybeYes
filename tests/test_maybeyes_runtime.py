import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from skill.scripts.maybeyes import MaybeYesRuntime


class MaybeYesRuntimeTest(unittest.TestCase):
    def runtime(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return MaybeYesRuntime(Path(temp.name)), Path(temp.name)

    def test_source_edit_with_rollback_is_optimistic_b(self):
        runtime, state_dir = self.runtime()

        result = runtime.decide(
            action="edit src/payment/client.py and tests/test_payment.py",
            action_type="file_edit",
            files=["src/payment/client.py", "tests/test_payment.py"],
            user_intent="fix payment timeout and add tests",
            rollback="discard patch",
        )

        self.assertEqual(result["class"], "B")
        self.assertEqual(result["decision"], "optimistic_execute")
        self.assertGreaterEqual(result["confidence"], 0.5)
        events = (state_dir / "ledger.jsonl").read_text().strip().splitlines()
        self.assertEqual(len(events), 1)

    def test_force_push_never_auto_executes(self):
        runtime, _ = self.runtime()

        result = runtime.decide(
            action="git push --force origin main",
            action_type="command",
            branch="main",
            user_intent="publish changes",
        )

        self.assertEqual(result["class"], "D")
        self.assertEqual(result["decision"], "ask_now")
        self.assertEqual(result["confidence"], 0.0)

    def test_env_read_is_not_ordinary_a(self):
        runtime, _ = self.runtime()

        result = runtime.decide(
            action="read .env",
            action_type="read",
            files=[".env"],
            user_intent="inspect config",
        )

        self.assertEqual(result["class"], "D")
        self.assertEqual(result["decision"], "ask_now")

    def test_prod_deploy_and_database_migration_ask_first(self):
        runtime, _ = self.runtime()

        deploy = runtime.decide(
            action="deploy production",
            action_type="command",
            production=True,
            user_intent="ship release",
        )
        migration = runtime.decide(
            action="run database migration",
            action_type="command",
            production=True,
            user_intent="ship release",
        )

        self.assertEqual(deploy["class"], "D")
        self.assertEqual(migration["class"], "D")
        self.assertEqual(deploy["decision"], "ask_now")
        self.assertEqual(migration["decision"], "ask_now")

    def test_feature_branch_push_is_c1_with_strict_checks(self):
        runtime, _ = self.runtime()

        result = runtime.decide(
            action="git push origin feature/payment-timeout",
            action_type="command",
            branch="feature/payment-timeout",
            user_intent="push current feature branch",
            undoable=True,
        )

        self.assertEqual(result["class"], "C1")
        self.assertEqual(result["decision"], "optimistic_execute")
        self.assertGreaterEqual(result["confidence"], 0.85)

    def test_retrains_when_model_is_older_than_24_hours(self):
        runtime, state_dir = self.runtime()
        old = datetime.now(timezone.utc) - timedelta(hours=25)
        (state_dir / "model.json").write_text(json.dumps({"trained_at": old.isoformat(), "weights": {}}))
        (state_dir / "feedback.jsonl").write_text(
            json.dumps(
                {
                    "label": "explicit_approve",
                    "class": "B",
                    "action_type": "file_edit",
                    "features": ["class:B", "action_type:file_edit"],
                }
            )
            + "\n"
        )

        runtime.maybe_retrain()
        model = json.loads((state_dir / "model.json").read_text())

        self.assertNotEqual(model["trained_at"], old.isoformat())
        self.assertIn("class:B", model["weights"])


if __name__ == "__main__":
    unittest.main()
