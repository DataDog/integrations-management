# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from collections.abc import Sequence
from unittest.mock import patch as mock_patch

from azure_integration_quickstart.permissions import FlatPermission
from azure_integration_quickstart.scopes import (
    ManagementGroupListResult,
    Scope,
    Subscription,
    _collect_subscriptions_from_children,
    filter_scopes_by_permission,
    flatten_scopes,
    get_available_regions,
    get_management_group_from_list_result,
)

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
                self.assertEqual(mock_get_flat_permission.call_count, len(scope_permissions))
                self.assertListEqual(actual, expected_result)


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


class TestGetAvailableRegions(DDTestCase):
    def test_get_available_regions(self):
        """Test that get_available_regions returns a list of region names."""
        expected_regions = [
            "eastus",
            "eastus2",
            "westus",
            "westus2",
            "centralus",
            "northeurope",
            "westeurope",
        ]
        with mock_patch("az_shared.regions.execute_json") as mock_execute_json:
            mock_execute_json.return_value = expected_regions
            regions = get_available_regions()
            self.assertIsNotNone(regions)
            self.assertGreater(len(regions), 0)
            self.assertEqual(regions, expected_regions)
            mock_execute_json.assert_called_once()


class TestCollectSubscriptionsFromChildren(DDTestCase):
    """Tests for _collect_subscriptions_from_children with varying hierarchy structures."""

    def test_management_group_with_no_children(self):
        """Children key is present but empty list."""
        node = {
            "id": "/providers/Microsoft.Management/managementGroups/EmptyMg",
            "name": "EmptyMg",
            "displayName": "Empty MG",
            "children": [],
        }
        actual = _collect_subscriptions_from_children(node)
        self.assertEqual(actual, [])

    def test_direct_subscriptions_only(self):
        """Root has only subscription children (no nested management groups)."""
        node = {
            "id": "/providers/Microsoft.Management/managementGroups/Root",
            "children": [
                {
                    "id": "/subscriptions/sub-1",
                    "name": "sub-1",
                    "displayName": "Sub One",
                },
                {
                    "id": "/subscriptions/sub-2",
                    "name": "sub-2",
                    "displayName": "Sub Two",
                },
            ],
        }
        actual = _collect_subscriptions_from_children(node)
        expected = [
            Subscription(id="sub-1", name="Sub One"),
            Subscription(id="sub-2", name="Sub Two"),
        ]
        self.assert_same_scopes(actual, expected)

    def test_nested_management_group_with_subscriptions(self):
        """Root > child management group > subscriptions."""
        node = {
            "id": "/providers/Microsoft.Management/managementGroups/TenantRoot",
            "children": [
                {
                    "id": "/providers/Microsoft.Management/managementGroups/ChildMg",
                    "children": [
                        {
                            "id": "/subscriptions/sub-a",
                            "name": "sub-a",
                            "displayName": "Sub A",
                        },
                    ],
                },
            ],
        }
        actual = _collect_subscriptions_from_children(node)
        expected = [Subscription(id="sub-a", name="Sub A")]
        self.assert_same_scopes(actual, expected)

    def test_tenant_root_with_multiple_sub_mgs_each_with_subscriptions(self):
        """Tenant root with multiple child management groups, each containing subscriptions."""
        node = {
            "id": "/providers/Microsoft.Management/managementGroups/TenantRoot",
            "children": [
                {
                    "id": "/providers/Microsoft.Management/managementGroups/Mg1",
                    "children": [
                        {
                            "id": "/subscriptions/s1",
                            "name": "s1",
                            "displayName": "Team A Sub",
                        },
                    ],
                },
                {
                    "id": "/providers/Microsoft.Management/managementGroups/Mg2",
                    "children": [
                        {
                            "id": "/subscriptions/s2",
                            "name": "s2",
                            "displayName": "Team B Sub 1",
                        },
                        {
                            "id": "/subscriptions/s3",
                            "name": "s3",
                            "displayName": "Team B Sub 2",
                        },
                    ],
                },
            ],
        }
        actual = _collect_subscriptions_from_children(node)
        expected = [
            Subscription(id="s1", name="Team A Sub"),
            Subscription(id="s2", name="Team B Sub 1"),
            Subscription(id="s3", name="Team B Sub 2"),
        ]
        self.assert_same_scopes(actual, expected)

    def test_mixed_direct_and_nested_subscriptions(self):
        """Root has both direct subscription children and a child MG with subscriptions."""
        node = {
            "id": "/providers/Microsoft.Management/managementGroups/Root",
            "children": [
                {
                    "id": "/subscriptions/direct-1",
                    "name": "direct-1",
                    "displayName": "Direct Sub",
                },
                {
                    "id": "/providers/Microsoft.Management/managementGroups/ChildMg",
                    "children": [
                        {
                            "id": "/subscriptions/nested-1",
                            "name": "nested-1",
                            "displayName": "Nested Sub",
                        },
                    ],
                },
            ],
        }
        actual = _collect_subscriptions_from_children(node)
        expected = [
            Subscription(id="direct-1", name="Direct Sub"),
            Subscription(id="nested-1", name="Nested Sub"),
        ]
        self.assert_same_scopes(actual, expected)

    def test_empty_dict_uses_default_children(self):
        """Node with no children key (e.g. response or {} fallback) returns empty list."""
        node = {}
        actual = _collect_subscriptions_from_children(node)
        self.assertEqual(actual, [])


class TestGetManagementGroupFromListResult(DDTestCase):
    """Tests for get_management_group_from_list_result with mocked show response."""

    def test_show_response_with_nested_subscriptions(self):
        """Show returns nested tree (root > child MG > subs); id/name from list_result, subscriptions from tree."""
        list_result = ManagementGroupListResult(
            id="/providers/Microsoft.Management/managementGroups/TenantRoot",
            name="Tenant Root",
            az_name="TenantRoot",
        )
        show_response = {
            "id": "/providers/Microsoft.Management/managementGroups/TenantRoot",
            "children": [
                {
                    "id": "/providers/Microsoft.Management/managementGroups/ChildMg",
                    "children": [
                        {
                            "id": "/subscriptions/sub-1",
                            "name": "sub-1",
                            "displayName": "Prod Sub",
                        },
                    ],
                },
            ],
        }
        with mock_patch("azure_integration_quickstart.scopes.execute_json") as mock_execute_json:
            mock_execute_json.return_value = show_response
            mg = get_management_group_from_list_result(list_result)
        self.assertEqual(mg.id, "/providers/Microsoft.Management/managementGroups/TenantRoot")
        self.assertEqual(mg.name, "Tenant Root")
        self.assert_same_scopes(mg.subscriptions, [Subscription(id="sub-1", name="Prod Sub")])

    def test_management_group_with_no_children(self):
        """Show response with children key present but empty list yields MG with empty subscriptions."""
        list_result = ManagementGroupListResult(
            id="/providers/Microsoft.Management/managementGroups/EmptyMg",
            name="Empty Management Group",
            az_name="EmptyMg",
        )
        show_response = {"id": "/providers/.../EmptyMg", "children": []}
        with mock_patch("azure_integration_quickstart.scopes.execute_json") as mock_execute_json:
            mock_execute_json.return_value = show_response
            mg = get_management_group_from_list_result(list_result)
        self.assertEqual(mg.subscriptions, [])

    def test_uses_properties_children_when_children_not_at_top_level(self):
        """When show returns children under properties, normalization still finds them."""
        list_result = ManagementGroupListResult(
            id="/providers/Microsoft.Management/managementGroups/Mg",
            name="MG",
            az_name="Mg",
        )
        show_response = {
            "id": "/providers/Microsoft.Management/managementGroups/Mg",
            "properties": {
                "children": [
                    {
                        "id": "/subscriptions/psub",
                        "name": "psub",
                        "displayName": "Props Sub",
                    },
                ],
            },
        }
        with mock_patch("azure_integration_quickstart.scopes.execute_json") as mock_execute_json:
            mock_execute_json.return_value = show_response
            mg = get_management_group_from_list_result(list_result)
        self.assert_same_scopes(mg.subscriptions, [Subscription(id="psub", name="Props Sub")])

    def test_show_response_none_yields_empty_subscriptions(self):
        """When execute_json returns None (e.g. CLI failure), MG has empty subscriptions."""
        list_result = ManagementGroupListResult(
            id="/providers/Microsoft.Management/managementGroups/Mg",
            name="MG",
            az_name="Mg",
        )
        with mock_patch("azure_integration_quickstart.scopes.execute_json") as mock_execute_json:
            mock_execute_json.return_value = None
            mg = get_management_group_from_list_result(list_result)
        self.assertEqual(mg.subscriptions, [])

    def test_direct_subscriptions_only(self):
        """Show response with only direct subscription children (no nested MGs)."""
        list_result = ManagementGroupListResult(
            id="/providers/Microsoft.Management/managementGroups/Root",
            name="Root",
            az_name="Root",
        )
        show_response = {
            "id": "/providers/.../Root",
            "children": [
                {"id": "/subscriptions/d1", "name": "d1", "displayName": "Direct One"},
                {"id": "/subscriptions/d2", "name": "d2", "displayName": "Direct Two"},
            ],
        }
        with mock_patch("azure_integration_quickstart.scopes.execute_json") as mock_execute_json:
            mock_execute_json.return_value = show_response
            mg = get_management_group_from_list_result(list_result)
        self.assert_same_scopes(
            mg.subscriptions,
            [
                Subscription(id="d1", name="Direct One"),
                Subscription(id="d2", name="Direct Two"),
            ],
        )

    def test_tenant_root_with_multiple_sub_mgs_each_with_subscriptions(self):
        """Show response: tenant root with multiple child MGs, each with subscriptions."""
        list_result = ManagementGroupListResult(
            id="/providers/Microsoft.Management/managementGroups/TenantRoot",
            name="Tenant Root",
            az_name="TenantRoot",
        )
        show_response = {
            "id": "/providers/.../TenantRoot",
            "children": [
                {
                    "id": "/providers/.../Mg1",
                    "children": [
                        {"id": "/subscriptions/s1", "name": "s1", "displayName": "Team A Sub"},
                    ],
                },
                {
                    "id": "/providers/.../Mg2",
                    "children": [
                        {"id": "/subscriptions/s2", "name": "s2", "displayName": "Team B Sub 1"},
                        {"id": "/subscriptions/s3", "name": "s3", "displayName": "Team B Sub 2"},
                    ],
                },
            ],
        }
        with mock_patch("azure_integration_quickstart.scopes.execute_json") as mock_execute_json:
            mock_execute_json.return_value = show_response
            mg = get_management_group_from_list_result(list_result)
        self.assert_same_scopes(
            mg.subscriptions,
            [
                Subscription(id="s1", name="Team A Sub"),
                Subscription(id="s2", name="Team B Sub 1"),
                Subscription(id="s3", name="Team B Sub 2"),
            ],
        )
