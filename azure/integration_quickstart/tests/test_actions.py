# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase

from azure_integration_quickstart.actions import Action, ActionContainer, is_action_lte, is_action_overlapping


class TestActions(TestCase):
    def test_is_action_lte(self):
        test_cases: list[tuple[str, Action, Action, bool]] = [
            ("a < b", "Microsoft.Compute/virtualMachines/read", "*/read", True),
            ("a > b", "*/read", "Microsoft.Compute/virtualMachines/read", False),
            ("a == b", "*/read", "*/read", True),
            ("unrelated", "*/read", "Microsoft.Compute/virtualMachines/*", False),
        ]

        for name, action_a, action_b, expected_result in test_cases:
            with self.subTest(msg=name):
                actual = is_action_lte(action_a, action_b)
                self.assertEqual(actual, expected_result)

    def test_is_action_overlapping(self):
        test_cases: list[tuple[str, Action, Action, bool]] = [
            ("a < b", "Microsoft.Compute/virtualMachines/read", "*/read", True),
            ("a > b", "*/read", "Microsoft.Compute/virtualMachines/read", True),
            ("a == b", "*/read", "*/read", True),
            ("unrelated", "*/read", "Microsoft.Compute/virtualMachines/*", False),
        ]

        for name, action_a, action_b, expected_result in test_cases:
            with self.subTest(msg=name):
                actual = is_action_overlapping(action_a, action_b)
                self.assertEqual(actual, expected_result)

    def test_contains_action(self):
        test_cases: list[tuple[str, ActionContainer, Action, bool]] = [
            ("empty", ActionContainer([], []), "Microsoft.Compute/virtualMachines/read", False),
            (
                "no match",
                ActionContainer(["Microsoft.Compute/virtualMachines/write"], []),
                "Microsoft.Compute/virtualMachines/read",
                False,
            ),
            (
                "exact match",
                ActionContainer(
                    ["Microsoft.Compute/virtualMachines/write", "Microsoft.Compute/virtualMachines/read"], []
                ),
                "Microsoft.Compute/virtualMachines/read",
                True,
            ),
            (
                "lt match",
                ActionContainer(["Microsoft.Compute/virtualMachines/*"], []),
                "Microsoft.Compute/virtualMachines/read",
                True,
            ),
            (
                "multiple matches",
                ActionContainer(["Microsoft.Compute/virtualMachines/read", "Microsoft.Compute/virtualMachines/*"], []),
                "Microsoft.Compute/virtualMachines/read",
                True,
            ),
            (
                "greater not action",
                ActionContainer(["Microsoft.Compute/virtualMachines/read"], ["Microsoft.Compute/*/*"]),
                "Microsoft.Compute/virtualMachines/*",
                False,
            ),
            (
                "less than not action",
                ActionContainer(
                    ["Microsoft.Compute/virtualMachines/read"], ["Microsoft.Compute/virtualMachines/write"]
                ),
                "Microsoft.Compute/virtualMachines/*",
                False,
            ),
            (
                "equal not action",
                ActionContainer([], ["Microsoft.Compute/virtualMachines/*"]),
                "Microsoft.Compute/virtualMachines/*",
                False,
            ),
            (
                "unrelated not action",
                ActionContainer(["Microsoft.Compute/virtualMachines/*"], ["Microsoft.Compute/analogMachines/read"]),
                "Microsoft.Compute/virtualMachines/read",
                True,
            ),
        ]

        for name, container, action, expected_result in test_cases:
            with self.subTest(msg=name):
                actual = action in container
                self.assertEqual(actual, expected_result)
