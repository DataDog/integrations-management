# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase

from azure_lfo_consumption_plan_migration.steps import RollbackError, Runner, Step


class TestRunner(TestCase):
    def test_runs_steps_in_order(self) -> None:
        order: list[str] = []
        runner = Runner()
        runner.run(Step("a", do=lambda: order.append("a"), undo=lambda: order.append("undo-a")))
        runner.run(Step("b", do=lambda: order.append("b"), undo=lambda: order.append("undo-b")))
        self.assertEqual(order, ["a", "b"])

    def test_rolls_back_completed_steps_in_reverse_on_failure(self) -> None:
        order: list[str] = []
        runner = Runner()
        runner.run(Step("a", do=lambda: order.append("a"), undo=lambda: order.append("undo-a")))
        runner.run(Step("b", do=lambda: order.append("b"), undo=lambda: order.append("undo-b")))

        def boom() -> None:
            order.append("c-attempt")
            raise RuntimeError("boom")

        with self.assertRaises(RollbackError):
            runner.run(Step("c", do=boom, undo=lambda: order.append("undo-c")))

        # c's undo must NOT run because c was never marked completed.
        self.assertEqual(order, ["a", "b", "c-attempt", "undo-b", "undo-a"])

    def test_step_with_no_undo_is_skipped_during_rollback(self) -> None:
        order: list[str] = []
        runner = Runner()
        runner.run(Step("a", do=lambda: order.append("a"), undo=lambda: order.append("undo-a")))
        runner.run(Step("noop", do=lambda: order.append("noop")))  # undo=None

        with self.assertRaises(RollbackError):
            runner.run(
                Step(
                    "boom",
                    do=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
                    undo=lambda: order.append("undo-boom"),
                )
            )

        self.assertEqual(order, ["a", "noop", "undo-a"])

    def test_run_best_effort_collects_manual_actions_on_failure(self) -> None:
        runner = Runner()

        def boom() -> None:
            raise RuntimeError("nope")

        runner.run_best_effort(Step("step1", do=boom), "do the thing manually")
        self.assertEqual(len(runner.manual_actions), 1)
        self.assertIn("step1", runner.manual_actions[0])
        self.assertIn("do the thing manually", runner.manual_actions[0])

    def test_run_best_effort_swallows_success_silently(self) -> None:
        runner = Runner()
        runner.run_best_effort(Step("step1", do=lambda: None), "shouldn't be needed")
        self.assertEqual(runner.manual_actions, [])

    def test_rollback_failure_appended_to_manual_actions(self) -> None:
        runner = Runner()

        def bad_undo() -> None:
            raise RuntimeError("undo failed")

        runner.run(Step("a", do=lambda: None, undo=bad_undo))

        with self.assertRaises(RollbackError):
            runner.run(
                Step(
                    "b",
                    do=lambda: (_ for _ in ()).throw(RuntimeError("forward failed")),
                    undo=lambda: None,
                )
            )

        self.assertTrue(any("Rollback of 'a' failed" in msg for msg in runner.manual_actions))
