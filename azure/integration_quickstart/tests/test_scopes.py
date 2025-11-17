# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from collections.abc import Sequence
from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import patch as mock_patch

from azure_integration_quickstart.permissions import FlatPermission
from azure_integration_quickstart.scopes import Scope, Subscription, filter_scopes_by_permission, flatten_scopes

from integration_quickstart.tests.dd_test_case import DDTestCase
from integration_quickstart.tests.test_data import (
    EXAMPLE_MANAGEMENT_GROUP_EMPTY_SCOPE,
    EXAMPLE_MANAGEMENT_GROUP_OVERLAP_SCOPE,
    EXAMPLE_MANAGEMENT_GROUP_SCOPE,
    EXAMPLE_SUBSCRIPTION_SCOPES,
    FLAT_PERMISSION_ASSIGN_ROLES,
    FLAT_PERMISSION_EMPTY,
    FLAT_PERMISSION_NO_ASSIGN_ROLES,
)


def make_flat_permissions_mock_impl(scopes_with_permissions: list[tuple[Scope, FlatPermission]]):
    result_dict = {scope.scope: permission for scope, permission in scopes_with_permissions}

    def mock_impl(_auth_token: str, scope: str):
        return result_dict[scope]

    return mock_impl


class TestFilterScopesByPermission(DDTestCase):
    def setUp(self) -> None:
        self.az_cmd_mock: MagicMock = self.patch("azure_integration_quickstart.scopes.execute_json")
        self.az_cmd_mock.return_value = {"accessToken": ""}

    def test_filter_scopes_by_permission(self):
        test_cases: list[tuple[str, list[tuple[Scope, FlatPermission]], list[Scope]]] = [
            ("no_scopes", [], []),
            (
                "all_missing_permissions",
                [
                    (EXAMPLE_SUBSCRIPTION_SCOPES[0], FLAT_PERMISSION_EMPTY),
                    (EXAMPLE_SUBSCRIPTION_SCOPES[1], FLAT_PERMISSION_NO_ASSIGN_ROLES),
                    (EXAMPLE_SUBSCRIPTION_SCOPES[2], FLAT_PERMISSION_NO_ASSIGN_ROLES),
                ],
                [],
            ),
            (
                "all_have_permission",
                [
                    (EXAMPLE_SUBSCRIPTION_SCOPES[0], FLAT_PERMISSION_ASSIGN_ROLES),
                    (EXAMPLE_SUBSCRIPTION_SCOPES[1], FLAT_PERMISSION_ASSIGN_ROLES),
                    (EXAMPLE_MANAGEMENT_GROUP_SCOPE, FLAT_PERMISSION_ASSIGN_ROLES),
                ],
                [EXAMPLE_SUBSCRIPTION_SCOPES[0], EXAMPLE_SUBSCRIPTION_SCOPES[1], EXAMPLE_MANAGEMENT_GROUP_SCOPE],
            ),
            (
                "one_has_permission",
                [
                    (EXAMPLE_SUBSCRIPTION_SCOPES[0], FLAT_PERMISSION_NO_ASSIGN_ROLES),
                    (EXAMPLE_SUBSCRIPTION_SCOPES[1], FLAT_PERMISSION_ASSIGN_ROLES),
                    (EXAMPLE_MANAGEMENT_GROUP_SCOPE, FLAT_PERMISSION_EMPTY),
                ],
                [EXAMPLE_SUBSCRIPTION_SCOPES[1]],
            ),
        ]

        for name, scope_permissions, expected_result in test_cases:
            with self.subTest(msg=name):
                mock_get_flat_permission_impl = make_flat_permissions_mock_impl(scope_permissions)
                with mock_patch(
                    "azure_integration_quickstart.scopes.get_flat_permission", wraps=mock_get_flat_permission_impl
                ) as mock_get_flat_permission:
                    actual = filter_scopes_by_permission([scope for scope, _ in scope_permissions])
                self.az_cmd_mock.assert_called_once()
                self.assertEqual(mock_get_flat_permission.call_count, len(scope_permissions))
                self.assertListEqual(actual, expected_result)

            self.az_cmd_mock.reset_mock()


class TestFlattenScopes(DDTestCase):
    def test_flatten_scopes(self):
        test_cases: list[tuple[str, Sequence[Scope], set[Subscription]]] = [
            ("empty", [], set()),
            (
                "single management group",
                [EXAMPLE_MANAGEMENT_GROUP_SCOPE],
                {EXAMPLE_SUBSCRIPTION_SCOPES[0], EXAMPLE_SUBSCRIPTION_SCOPES[1]},
            ),
            (
                "multiple subscriptions",
                [EXAMPLE_SUBSCRIPTION_SCOPES[0], EXAMPLE_SUBSCRIPTION_SCOPES[2]],
                {EXAMPLE_SUBSCRIPTION_SCOPES[0], EXAMPLE_SUBSCRIPTION_SCOPES[2]},
            ),
            (
                "no overlap",
                [EXAMPLE_MANAGEMENT_GROUP_EMPTY_SCOPE, EXAMPLE_SUBSCRIPTION_SCOPES[0], EXAMPLE_SUBSCRIPTION_SCOPES[1]],
                {EXAMPLE_SUBSCRIPTION_SCOPES[0], EXAMPLE_SUBSCRIPTION_SCOPES[1]},
            ),
            (
                "overlap mgroup with sub",
                [EXAMPLE_MANAGEMENT_GROUP_SCOPE, EXAMPLE_SUBSCRIPTION_SCOPES[0], EXAMPLE_SUBSCRIPTION_SCOPES[2]],
                {EXAMPLE_SUBSCRIPTION_SCOPES[0], EXAMPLE_SUBSCRIPTION_SCOPES[1], EXAMPLE_SUBSCRIPTION_SCOPES[2]},
            ),
            (
                "overlap mgroup with mgroup",
                [EXAMPLE_MANAGEMENT_GROUP_SCOPE, EXAMPLE_MANAGEMENT_GROUP_OVERLAP_SCOPE],
                {EXAMPLE_SUBSCRIPTION_SCOPES[0], EXAMPLE_SUBSCRIPTION_SCOPES[1], EXAMPLE_SUBSCRIPTION_SCOPES[2]},
            ),
        ]
        for name, scopes, expected_result in test_cases:
            with self.subTest(msg=name):
                actual = flatten_scopes(scopes)
                self.assert_same_scopes(actual, expected_result)
