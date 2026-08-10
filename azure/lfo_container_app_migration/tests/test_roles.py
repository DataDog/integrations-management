# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase
from unittest.mock import patch as mock_patch

from azure_lfo_container_app_migration.roles import (
    as_container_app_job_control_plane,
    build_role_steps,
)
from azure_logging_install.configuration import ControlPlaneType

from caj_migration.tests.test_data import (
    DEPLOYER_JOB_NAME,
    DIAGNOSTIC_SETTINGS_TASK_CONTAINER_APP_JOB_NAME,
    SUB_1_ID,
    SUB_2_ID,
    make_function_app_control_plane,
)


class TestAsContainerAppJobControlPlane(TestCase):
    def test_swaps_type_and_recomputes_task_names(self):
        control_plane = make_function_app_control_plane()

        caj_control_plane = as_container_app_job_control_plane(control_plane)

        self.assertEqual(caj_control_plane.type, ControlPlaneType.ContainerAppJobs)
        self.assertEqual(caj_control_plane.diagnostic_settings_task_name, DIAGNOSTIC_SETTINGS_TASK_CONTAINER_APP_JOB_NAME)
        # resources/scaling task names are unchanged between control plane types
        self.assertEqual(caj_control_plane.resources_task_name, control_plane.resources_task_name)
        self.assertEqual(caj_control_plane.scaling_task_name, control_plane.scaling_task_name)


class TestBuildRoleSteps(TestCase):
    def setUp(self) -> None:
        self.control_plane = make_function_app_control_plane()
        self.mock_grant = self.patch("azure_lfo_container_app_migration.roles.grant_subscriptions_permissions")
        self.mock_get_principal_id = self.patch("azure_lfo_container_app_migration.roles.get_container_app_job_principal_id")
        self.mock_assign_role = self.patch("azure_lfo_container_app_migration.roles.assign_role")
        self.mock_remove_role = self.patch("azure_lfo_container_app_migration.roles.remove_role")
        self.mock_get_principal_id.return_value = "deployer-principal-id"

    def patch(self, path: str, **kwargs):
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_grant_step_calls_grant_subscriptions_permissions_with_caj_type(self):
        steps = build_role_steps(self.control_plane, DEPLOYER_JOB_NAME, [SUB_1_ID, SUB_2_ID])
        steps[0].action()

        self.mock_grant.assert_called_once()
        caj_control_plane_arg = self.mock_grant.call_args.args[0]
        self.assertEqual(caj_control_plane_arg.type, ControlPlaneType.ContainerAppJobs)
        self.assertEqual(self.mock_grant.call_args.args[1], [SUB_1_ID, SUB_2_ID])

    def test_grant_rollback_only_removes_role_assignments(self):
        steps = build_role_steps(self.control_plane, DEPLOYER_JOB_NAME, [SUB_1_ID])

        steps[0].rollback()

        # rollback should only call remove_role for each of the 4 role/scope tuples -
        # never anything that deletes the pre-existing monitored subscription's resource group.
        self.assertEqual(self.mock_remove_role.call_count, 4)

    def test_deployer_role_step_assigns_container_apps_jobs_contributor(self):
        steps = build_role_steps(self.control_plane, DEPLOYER_JOB_NAME, [SUB_1_ID])
        steps[1].action()

        self.mock_assign_role.assert_called_once()
        from azure_logging_install.constants import CONTAINER_APPS_JOBS_CONTRIBUTOR_ID

        self.assertEqual(self.mock_assign_role.call_args.args[1], "deployer-principal-id")
        self.assertEqual(self.mock_assign_role.call_args.args[2], CONTAINER_APPS_JOBS_CONTRIBUTOR_ID)

    def test_deployer_role_rollback_removes_the_same_role(self):
        steps = build_role_steps(self.control_plane, DEPLOYER_JOB_NAME, [SUB_1_ID])
        steps[1].rollback()

        from azure_logging_install.constants import CONTAINER_APPS_JOBS_CONTRIBUTOR_ID

        self.mock_remove_role.assert_called_once()
        self.assertEqual(self.mock_remove_role.call_args.args[1], "deployer-principal-id")
        self.assertEqual(self.mock_remove_role.call_args.args[2], CONTAINER_APPS_JOBS_CONTRIBUTOR_ID)
