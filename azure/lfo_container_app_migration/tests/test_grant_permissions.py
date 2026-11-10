# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase
from unittest.mock import patch as mock_patch

from azure_logging_install.configuration import Configuration, ControlPlane, ControlPlaneType
from azure_logging_install.constants import CONTAINER_APPS_JOBS_CONTRIBUTOR

from azure_lfo_container_app_migration.grant_permissions import GrantContainerAppJobPermissionsStep, resource_group_exists

CONTROL_PLANE_ID = "abcdef123456"
SUBSCRIPTION_ID = "test-sub"
RESOURCE_GROUP = "test-rg"
REGION = "eastus"
DEPLOYER_PRINCIPAL_ID = "deployer-principal-id"


class TestGrantContainerAppJobPermissionsStep(TestCase):
    def setUp(self) -> None:
        self.grant_permissions_mock = self.patch("azure_lfo_container_app_migration.grant_permissions.grant_permissions")
        self.get_principal_id_mock = self.patch(
            "azure_lfo_container_app_migration.grant_permissions.get_container_app_job_principal_id",
            return_value=DEPLOYER_PRINCIPAL_ID,
        )
        self.remove_role_mock = self.patch("azure_lfo_container_app_migration.grant_permissions.remove_role")
        self.revoke_subscriptions_role_assignments_mock = self.patch(
            "azure_lfo_container_app_migration.grant_permissions.revoke_subscriptions_role_assignments"
        )

        self.config = Configuration(
            control_plane=ControlPlane(
                id=CONTROL_PLANE_ID,
                sub_id=SUBSCRIPTION_ID,
                resource_group=RESOURCE_GROUP,
                region=REGION,
                type=ControlPlaneType.ContainerAppJobs,
            ),
            monitored_subs="sub-1,sub-2",
            datadog_api_key="test-api-key",
        )

    def patch(self, path: str, **kwargs):
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_execute_grants_permissions(self):
        step = GrantContainerAppJobPermissionsStep(self.config)

        step.execute()

        self.grant_permissions_mock.assert_called_once_with(self.config)

    def test_rollback_revokes_deployer_role_and_subscription_permissions(self):
        step = GrantContainerAppJobPermissionsStep(self.config)

        step.rollback()

        self.get_principal_id_mock.assert_called_once_with(RESOURCE_GROUP, SUBSCRIPTION_ID, self.config.deployer_job_name)
        self.remove_role_mock.assert_called_once_with(
            self.config.control_plane_rg_scope, DEPLOYER_PRINCIPAL_ID, CONTAINER_APPS_JOBS_CONTRIBUTOR
        )
        self.revoke_subscriptions_role_assignments_mock.assert_called_once_with(
            self.config.control_plane, self.config.all_subscriptions
        )

    def test_describe_lists_every_subscription_and_missing_resource_groups_without_granting(self):
        self.patch(
            "azure_lfo_container_app_migration.grant_permissions.resource_group_exists",
            side_effect=lambda rg, sub_id: sub_id != "sub-2",
        )
        step = GrantContainerAppJobPermissionsStep(self.config)

        description = step.describe()

        self.assertIn(f"Subscription {SUBSCRIPTION_ID} (control plane): resource group '{RESOURCE_GROUP}' exists", description)
        self.assertIn(f"Subscription sub-1: resource group '{RESOURCE_GROUP}' exists", description)
        self.assertIn(f"Subscription sub-2: resource group '{RESOURCE_GROUP}' does not exist, would be created", description)
        self.assertIn("Container Apps Jobs Contributor", description)
        self.grant_permissions_mock.assert_not_called()

    def test_describe_reports_subscriptions_that_cannot_be_checked_and_continues(self):
        def rg_exists(rg, sub_id):
            if sub_id == "sub-1":
                raise RuntimeError("Subscription 'sub-1' not found")
            return True

        self.patch("azure_lfo_container_app_migration.grant_permissions.resource_group_exists", side_effect=rg_exists)
        step = GrantContainerAppJobPermissionsStep(self.config)

        description = step.describe()

        self.assertIn("Subscription sub-1: resource group 'test-rg' could not be checked", description)
        self.assertIn("Subscription 'sub-1' not found", description)
        self.assertIn(f"Subscription sub-2: resource group '{RESOURCE_GROUP}' exists", description)


class TestResourceGroupExists(TestCase):
    def test_parses_az_group_exists_output(self):
        with mock_patch("azure_lfo_container_app_migration.grant_permissions.execute", return_value="true\n") as execute_mock:
            self.assertTrue(resource_group_exists(RESOURCE_GROUP, SUBSCRIPTION_ID))
        self.assertIn("group exists", str(execute_mock.call_args.args[0]))

        with mock_patch("azure_lfo_container_app_migration.grant_permissions.execute", return_value="false\n"):
            self.assertFalse(resource_group_exists(RESOURCE_GROUP, SUBSCRIPTION_ID))
