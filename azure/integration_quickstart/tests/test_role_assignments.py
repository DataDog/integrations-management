# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase
from unittest.mock import MagicMock, call, patch

from az_shared.errors import AccessError, ResourceNotFoundError
from azure_integration_quickstart.role_assignments import get_active_entra_role_ids

ROLE_A = "62e90394-69f5-4237-9190-012177145e10"  # Global Administrator
ROLE_B = "9b895d92-2cd3-44c7-9d02-a6ac2d5ea5c3"  # Application Administrator


class TestGetActiveEntraRoleIds(TestCase):
    @patch("azure_integration_quickstart.role_assignments.execute_json")
    def test_returns_union_of_permanent_and_pim_roles(self, mock_execute_json: MagicMock):
        mock_execute_json.side_effect = [[ROLE_A], [ROLE_B]]
        result = get_active_entra_role_ids("user-id")
        self.assertEqual(result, {ROLE_A, ROLE_B})

    @patch("azure_integration_quickstart.role_assignments.execute_json")
    def test_deduplicates_role_ids_present_in_both_calls(self, mock_execute_json: MagicMock):
        mock_execute_json.side_effect = [[ROLE_A], [ROLE_A]]
        result = get_active_entra_role_ids("user-id")
        self.assertEqual(result, {ROLE_A})

    @patch("azure_integration_quickstart.role_assignments.execute_json")
    def test_returns_permanent_roles_when_pim_call_raises_access_error(self, mock_execute_json: MagicMock):
        mock_execute_json.side_effect = [[ROLE_A], AccessError("Forbidden")]
        result = get_active_entra_role_ids("user-id")
        self.assertEqual(result, {ROLE_A})

    @patch("azure_integration_quickstart.role_assignments.execute_json")
    def test_returns_permanent_roles_when_pim_call_raises_resource_not_found(self, mock_execute_json: MagicMock):
        mock_execute_json.side_effect = [[ROLE_A], ResourceNotFoundError("404")]
        result = get_active_entra_role_ids("user-id")
        self.assertEqual(result, {ROLE_A})

    @patch("azure_integration_quickstart.role_assignments.execute_json")
    def test_returns_permanent_roles_when_pim_call_raises_runtime_error(self, mock_execute_json: MagicMock):
        mock_execute_json.side_effect = [[ROLE_A], RuntimeError("unexpected")]
        result = get_active_entra_role_ids("user-id")
        self.assertEqual(result, {ROLE_A})

    @patch("azure_integration_quickstart.role_assignments.execute_json")
    def test_returns_empty_set_when_user_has_no_roles(self, mock_execute_json: MagicMock):
        mock_execute_json.side_effect = [[], AccessError("Forbidden")]
        result = get_active_entra_role_ids("user-id")
        self.assertEqual(result, set())

    @patch("azure_integration_quickstart.role_assignments.execute_json")
    def test_graph_calls_use_correct_endpoints(self, mock_execute_json: MagicMock):
        mock_execute_json.side_effect = [[], AccessError("Forbidden")]
        get_active_entra_role_ids("test-user-id")
        first_call_url = str(mock_execute_json.call_args_list[0])
        second_call_url = str(mock_execute_json.call_args_list[1])
        self.assertIn("roleAssignments", first_call_url)
        self.assertIn("roleAssignmentScheduleInstances", second_call_url)
        self.assertNotIn("azrbac.mspim", first_call_url)
        self.assertNotIn("azrbac.mspim", second_call_url)
