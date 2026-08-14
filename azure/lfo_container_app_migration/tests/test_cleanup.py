# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase
from unittest.mock import call, patch as mock_patch

from azure_logging_install.configuration import Configuration, ControlPlane, ControlPlaneType
from azure_logging_install.constants import WEBSITE_CONTRIBUTOR_ID

from azure_lfo_container_app_migration.cleanup import (
    DeleteControlPlaneCacheFileShare,
    DeleteOldFunctionApps,
    RevokeDeployerWebsiteContributorRole,
)

CONTROL_PLANE_ID = "abcdef123456"
SUBSCRIPTION_ID = "test-sub"
RESOURCE_GROUP = "test-rg"
REGION = "eastus"
DEPLOYER_PRINCIPAL_ID = "deployer-principal-id"


class CleanupTestCase(TestCase):
    def setUp(self) -> None:
        self.caj_config = Configuration(
            control_plane=ControlPlane(
                id=CONTROL_PLANE_ID,
                sub_id=SUBSCRIPTION_ID,
                resource_group=RESOURCE_GROUP,
                region=REGION,
                type=ControlPlaneType.ContainerAppJobs,
            ),
            monitored_subs="sub-1",
            datadog_api_key="test-api-key",
        )
        self.function_app_config = Configuration(
            control_plane=ControlPlane(
                id=CONTROL_PLANE_ID,
                sub_id=SUBSCRIPTION_ID,
                resource_group=RESOURCE_GROUP,
                region=REGION,
                type=ControlPlaneType.FunctionApps,
            ),
            monitored_subs="sub-1",
            datadog_api_key="test-api-key",
        )

    def patch(self, path: str, **kwargs):
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()


class TestDeleteOldFunctionApps(CleanupTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.delete_function_app_mock = self.patch("azure_lfo_container_app_migration.cleanup.delete_function_app")
        self.delete_empty_plans_mock = self.patch("azure_lfo_container_app_migration.cleanup.delete_empty_function_app_plans")

    def test_execute_deletes_all_three_function_apps_then_empty_plans(self):
        step = DeleteOldFunctionApps(self.function_app_config)
        step.execute()

        self.assertEqual(
            self.delete_function_app_mock.call_args_list,
            [call(name, RESOURCE_GROUP, SUBSCRIPTION_ID) for name in self.function_app_config.control_plane.task_names],
        )
        self.delete_empty_plans_mock.assert_called_once_with(RESOURCE_GROUP, SUBSCRIPTION_ID)


class TestDeleteControlPlaneCacheFileShare(CleanupTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.delete_file_share_mock = self.patch("azure_lfo_container_app_migration.cleanup.delete_file_share")

    def test_execute_deletes_the_file_share(self):
        step = DeleteControlPlaneCacheFileShare(self.caj_config)
        step.execute()

        self.delete_file_share_mock.assert_called_once_with(
            self.caj_config.control_plane_cache_storage_name, RESOURCE_GROUP, SUBSCRIPTION_ID
        )


class TestRevokeDeployerWebsiteContributorRole(CleanupTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.get_principal_id_mock = self.patch(
            "azure_lfo_container_app_migration.cleanup.get_container_app_job_principal_id",
            return_value=DEPLOYER_PRINCIPAL_ID,
        )
        self.remove_role_mock = self.patch("azure_lfo_container_app_migration.cleanup.remove_role")

    def test_execute_removes_the_website_contributor_role_assignment(self):
        step = RevokeDeployerWebsiteContributorRole(self.caj_config)
        step.execute()

        self.get_principal_id_mock.assert_called_once_with(RESOURCE_GROUP, SUBSCRIPTION_ID, self.caj_config.deployer_job_name)
        self.remove_role_mock.assert_called_once_with(
            self.caj_config.control_plane_rg_scope, DEPLOYER_PRINCIPAL_ID, WEBSITE_CONTRIBUTOR_ID
        )
