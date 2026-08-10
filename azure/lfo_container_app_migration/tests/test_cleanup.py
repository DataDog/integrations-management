# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase
from unittest.mock import patch as mock_patch

from azure_lfo_container_app_migration.cleanup import (
    cleanup_old_resources,
    get_function_app_service_plan_id,
)
from azure_logging_install.configuration import get_control_plane_cache_storage_name

from caj_migration.tests.test_data import (
    DEPLOYER_JOB_NAME,
    DIAGNOSTIC_SETTINGS_TASK_FUNCTION_APP_NAME,
    RESOURCES_TASK_NAME,
    SCALING_TASK_NAME,
    make_function_app_control_plane,
)


class TestGetFunctionAppServicePlanId(TestCase):
    def setUp(self) -> None:
        self.mock_execute = self.patch("azure_lfo_container_app_migration.cleanup.execute")
        self.control_plane = make_function_app_control_plane()

    def patch(self, path: str, **kwargs):
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_returns_plan_id(self):
        self.mock_execute.return_value = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Web/serverfarms/plan1\n"

        result = get_function_app_service_plan_id(RESOURCES_TASK_NAME, self.control_plane)

        self.assertEqual(result, "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Web/serverfarms/plan1")

    def test_returns_none_and_logs_on_failure(self):
        self.mock_execute.side_effect = Exception("boom")

        result = get_function_app_service_plan_id(RESOURCES_TASK_NAME, self.control_plane)

        self.assertIsNone(result)


class TestCleanupOldResources(TestCase):
    def setUp(self) -> None:
        self.control_plane = make_function_app_control_plane()
        self.mock_get_plan_id = self.patch("azure_lfo_container_app_migration.cleanup.get_function_app_service_plan_id")
        self.mock_delete_function_app = self.patch("azure_lfo_container_app_migration.cleanup.delete_function_app")
        self.mock_delete_plan = self.patch("azure_lfo_container_app_migration.cleanup.delete_app_service_plan")
        self.mock_delete_share = self.patch("azure_lfo_container_app_migration.cleanup.delete_control_plane_cache_file_share")
        self.mock_remove_role = self.patch("azure_lfo_container_app_migration.cleanup.remove_deployer_website_contributor_role")

    def patch(self, path: str, **kwargs):
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_happy_path_deletes_everything_and_returns_no_manual_cleanup(self):
        self.mock_get_plan_id.return_value = "shared-plan-id"

        result = cleanup_old_resources(self.control_plane, DEPLOYER_JOB_NAME)

        self.assertEqual(result, [])
        self.assertEqual(self.mock_delete_function_app.call_count, 3)
        deleted_names = {call.args[0] for call in self.mock_delete_function_app.call_args_list}
        self.assertEqual(
            deleted_names, {RESOURCES_TASK_NAME, SCALING_TASK_NAME, DIAGNOSTIC_SETTINGS_TASK_FUNCTION_APP_NAME}
        )
        # all 3 function apps share the same plan id, so it's only deleted once.
        self.mock_delete_plan.assert_called_once_with("shared-plan-id")
        self.mock_delete_share.assert_called_once_with(
            get_control_plane_cache_storage_name(self.control_plane.id), self.control_plane
        )
        self.mock_remove_role.assert_called_once_with(DEPLOYER_JOB_NAME, self.control_plane)

    def test_distinct_plan_ids_are_each_deleted_once(self):
        self.mock_get_plan_id.side_effect = ["plan-a", "plan-b", "plan-a"]

        cleanup_old_resources(self.control_plane, DEPLOYER_JOB_NAME)

        deleted_plan_ids = {call.args[0] for call in self.mock_delete_plan.call_args_list}
        self.assertEqual(deleted_plan_ids, {"plan-a", "plan-b"})
        self.assertEqual(self.mock_delete_plan.call_count, 2)

    def test_function_app_delete_failure_is_isolated_and_reported(self):
        self.mock_get_plan_id.return_value = None
        self.mock_delete_function_app.side_effect = [None, Exception("boom"), None]

        result = cleanup_old_resources(self.control_plane, DEPLOYER_JOB_NAME)

        self.assertEqual(len(result), 1)
        self.assertIn(SCALING_TASK_NAME, result[0])
        # other independent cleanup actions still ran despite the failure.
        self.mock_delete_share.assert_called_once()
        self.mock_remove_role.assert_called_once()

    def test_file_share_delete_failure_is_isolated_and_reported(self):
        self.mock_get_plan_id.return_value = None
        self.mock_delete_share.side_effect = Exception("share boom")

        result = cleanup_old_resources(self.control_plane, DEPLOYER_JOB_NAME)

        self.assertEqual(len(result), 1)
        self.assertIn("file share", result[0])
        self.mock_remove_role.assert_called_once()

    def test_role_removal_failure_is_isolated_and_reported(self):
        self.mock_get_plan_id.return_value = None
        self.mock_remove_role.side_effect = Exception("role boom")

        result = cleanup_old_resources(self.control_plane, DEPLOYER_JOB_NAME)

        self.assertEqual(len(result), 1)
        self.assertIn("Website Contributor", result[0])

    def test_plan_delete_failure_is_isolated_and_reported(self):
        self.mock_get_plan_id.return_value = "shared-plan-id"
        self.mock_delete_plan.side_effect = Exception("plan boom")

        result = cleanup_old_resources(self.control_plane, DEPLOYER_JOB_NAME)

        self.assertEqual(len(result), 1)
        self.assertIn("shared-plan-id", result[0])
        self.mock_delete_share.assert_called_once()
        self.mock_remove_role.assert_called_once()
