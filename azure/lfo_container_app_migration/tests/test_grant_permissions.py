# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase
from unittest.mock import patch as mock_patch

from azure_logging_install.configuration import Configuration, ControlPlane, ControlPlaneType
from azure_logging_install.constants import CONTAINER_APPS_JOBS_CONTRIBUTOR

from azure_lfo_container_app_migration.grant_permissions import GrantContainerAppJobPermissionsStep

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
