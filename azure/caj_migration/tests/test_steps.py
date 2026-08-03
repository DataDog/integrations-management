# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase

from azure_caj_migration.steps import Step, run_steps


class TestRunSteps(TestCase):
    def test_all_steps_succeed(self):
        calls = []
        steps = [
            Step(name="one", action=lambda: calls.append("one-action"), rollback=lambda: calls.append("one-rollback")),
            Step(name="two", action=lambda: calls.append("two-action"), rollback=lambda: calls.append("two-rollback")),
        ]

        run_steps(steps)

        self.assertEqual(calls, ["one-action", "two-action"])

    def test_default_rollback_is_noop(self):
        # Step() with no rollback specified should not raise when rolled back.
        calls = []

        def failing_action():
            raise RuntimeError("boom")

        steps = [
            Step(name="one", action=lambda: calls.append("one-action")),
            Step(name="two", action=failing_action),
        ]

        with self.assertRaises(RuntimeError):
            run_steps(steps)

        self.assertEqual(calls, ["one-action"])

    def test_failure_rolls_back_failed_step_then_preceding_steps_in_reverse(self):
        calls = []
        steps = [
            Step(name="one", action=lambda: calls.append("one-action"), rollback=lambda: calls.append("one-rollback")),
            Step(name="two", action=lambda: calls.append("two-action"), rollback=lambda: calls.append("two-rollback")),
            Step(
                name="three",
                action=self._raise("three-action failed", calls, "three-action"),
                rollback=lambda: calls.append("three-rollback"),
            ),
            Step(name="four", action=lambda: calls.append("four-action"), rollback=lambda: calls.append("four-rollback")),
        ]

        with self.assertRaises(RuntimeError):
            run_steps(steps)

        # Step four's action never runs (three failed first). Rollback order: three, then two, then one.
        self.assertEqual(
            calls,
            ["one-action", "two-action", "three-action", "three-rollback", "two-rollback", "one-rollback"],
        )

    def test_rollback_failure_does_not_prevent_other_rollbacks(self):
        calls = []

        def failing_rollback():
            calls.append("two-rollback-attempted")
            raise RuntimeError("rollback failed")

        steps = [
            Step(name="one", action=lambda: calls.append("one-action"), rollback=lambda: calls.append("one-rollback")),
            Step(name="two", action=lambda: calls.append("two-action"), rollback=failing_rollback),
            Step(
                name="three",
                action=self._raise("three-action failed", calls, "three-action"),
            ),
        ]

        with self.assertRaises(RuntimeError) as ctx:
            run_steps(steps)

        self.assertEqual(str(ctx.exception), "three-action failed")
        self.assertEqual(calls, ["one-action", "two-action", "three-action", "two-rollback-attempted", "one-rollback"])

    @staticmethod
    def _raise(message, calls, record_as):
        def action():
            calls.append(record_as)
            raise RuntimeError(message)

        return action
