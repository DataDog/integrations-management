# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase

from azure_integration_quickstart.actions import Action, is_action_lte, is_action_overlapping


class TestActions(TestCase):
    def test_is_action_lte(self):
        test_cases: list[tuple[str, Action, Action, bool]] = [
            ("a < b", "Microsoft.Compute/virtualMachines/read", "*/read", True),
            ("a > b", "*/read", "Microsoft.Compute/virtualMachines/read", False),
            ("a == b", "*/read", "*/read", True),
            ("unrelated", "*/read", "Microsoft.Compute/virtualMachines/*", False),
        ]

        for name, scope_a, scope_b, expected_result in test_cases:
            with self.subTest(msg=name):
                actual = is_action_lte(scope_a, scope_b)
                self.assertEqual(actual, expected_result)

    def test_is_action_overlapping(self):
        test_cases: list[tuple[str, Action, Action, bool]] = [
            ("a < b", "Microsoft.Compute/virtualMachines/read", "*/read", True),
            ("a > b", "*/read", "Microsoft.Compute/virtualMachines/read", True),
            ("a == b", "*/read", "*/read", True),
            ("unrelated", "*/read", "Microsoft.Compute/virtualMachines/*", False),
        ]

        for name, scope_a, scope_b, expected_result in test_cases:
            with self.subTest(msg=name):
                actual = is_action_overlapping(scope_a, scope_b)
                self.assertEqual(actual, expected_result)
