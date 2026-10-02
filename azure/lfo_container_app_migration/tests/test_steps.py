# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase

from azure_lfo_container_app_migration.steps import CleanupStep, Step, run_cleanup_steps, run_steps


class RecordingStep(Step):
    def __init__(self, name, calls, action=None, rollback=None):
        super().__init__(name)
        self.calls = calls
        self._action = action
        self._rollback = rollback

    def execute(self) -> None:
        if self._action:
            self._action()

    def rollback(self) -> None:
        if self._rollback:
            self._rollback()


class TestRunSteps(TestCase):
    def test_all_steps_succeed(self):
        calls = []
        steps = [
            RecordingStep("one", calls, action=lambda: calls.append("one-action"), rollback=lambda: calls.append("one-rollback")),
            RecordingStep("two", calls, action=lambda: calls.append("two-action"), rollback=lambda: calls.append("two-rollback")),
        ]

        run_steps(steps)

        self.assertEqual(calls, ["one-action", "two-action"])

    def test_default_rollback_is_noop(self):
        # A step with no rollback specified should not raise when rolled back.
        calls = []

        def failing_action():
            raise RuntimeError("boom")

        steps = [
            RecordingStep("one", calls, action=lambda: calls.append("one-action")),
            RecordingStep("two", calls, action=failing_action),
        ]

        with self.assertRaises(RuntimeError):
            run_steps(steps)

        self.assertEqual(calls, ["one-action"])

    def test_failure_rolls_back_failed_step_then_preceding_steps_in_reverse(self):
        calls = []
        steps = [
            RecordingStep("one", calls, action=lambda: calls.append("one-action"), rollback=lambda: calls.append("one-rollback")),
            RecordingStep("two", calls, action=lambda: calls.append("two-action"), rollback=lambda: calls.append("two-rollback")),
            RecordingStep(
                "three",
                calls,
                action=self._raise("three-action failed", calls, "three-action"),
                rollback=lambda: calls.append("three-rollback"),
            ),
            RecordingStep("four", calls, action=lambda: calls.append("four-action"), rollback=lambda: calls.append("four-rollback")),
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
            RecordingStep("one", calls, action=lambda: calls.append("one-action"), rollback=lambda: calls.append("one-rollback")),
            RecordingStep("two", calls, action=lambda: calls.append("two-action"), rollback=failing_rollback),
            RecordingStep(
                "three",
                calls,
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


class RecordingCleanupStep(CleanupStep):
    def __init__(self, name, calls, action=None):
        super().__init__(name)
        self.calls = calls
        self._action = action

    def execute(self) -> None:
        if self._action:
            self._action()


class TestRunCleanupSteps(TestCase):
    def test_all_steps_succeed(self):
        calls = []
        steps = [
            RecordingCleanupStep("one", calls, action=lambda: calls.append("one-action")),
            RecordingCleanupStep("two", calls, action=lambda: calls.append("two-action")),
        ]

        run_cleanup_steps(steps)

        self.assertEqual(calls, ["one-action", "two-action"])

    def test_a_failing_step_does_not_stop_or_raise_and_remaining_steps_still_run(self):
        calls = []

        def failing_action():
            calls.append("two-action")
            raise RuntimeError("boom")

        steps = [
            RecordingCleanupStep("one", calls, action=lambda: calls.append("one-action")),
            RecordingCleanupStep("two", calls, action=failing_action),
            RecordingCleanupStep("three", calls, action=lambda: calls.append("three-action")),
        ]

        run_cleanup_steps(steps)  # does not raise

        self.assertEqual(calls, ["one-action", "two-action", "three-action"])
