# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase
from unittest.mock import call, patch as mock_patch

from azure_logging_install.configuration import Configuration, ControlPlane, ControlPlaneType
from azure_logging_install.constants import DEPLOYER_TASK_CRON, DIAGNOSTIC_SETTINGS_TASK_CRON, RESOURCES_TASK_CRON, SCALING_TASK_CRON

from azure_lfo_container_app_migration.create_container_app_job import NEVER_RUN_CRON_EXPRESSION
from azure_lfo_container_app_migration.enablement import (
    PauseDeployer,
    PauseOldFunctionApps,
    UnpauseDeployer,
    UnpauseNewContainerAppJobs,
    UpdateDeployerImage,
)

CONTROL_PLANE_ID = "abcdef123456"
SUBSCRIPTION_ID = "test-sub"
RESOURCE_GROUP = "test-rg"
REGION = "eastus"


class EnablementTestCase(TestCase):
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


class TestPauseDeployer(EnablementTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.update_cron_mock = self.patch("azure_lfo_container_app_migration.enablement.update_container_app_job_cron_expression")

    def test_execute_sets_the_deployer_job_to_never_run(self):
        step = PauseDeployer(self.caj_config)
        step.execute()
        self.update_cron_mock.assert_called_once_with(
            self.caj_config.deployer_job_name, RESOURCE_GROUP, SUBSCRIPTION_ID, NEVER_RUN_CRON_EXPRESSION
        )

    def test_rollback_restores_the_deployer_jobs_real_cron(self):
        step = PauseDeployer(self.caj_config)
        step.rollback()
        self.update_cron_mock.assert_called_once_with(
            self.caj_config.deployer_job_name, RESOURCE_GROUP, SUBSCRIPTION_ID, DEPLOYER_TASK_CRON
        )


class TestPauseOldFunctionApps(EnablementTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.stop_mock = self.patch("azure_lfo_container_app_migration.enablement.stop_function_app")
        self.start_mock = self.patch("azure_lfo_container_app_migration.enablement.start_function_app")

    def test_execute_stops_all_three_old_function_apps(self):
        step = PauseOldFunctionApps(self.function_app_config)
        step.execute()
        self.assertEqual(
            self.stop_mock.call_args_list,
            [call(name, RESOURCE_GROUP, SUBSCRIPTION_ID) for name in self.function_app_config.control_plane.task_names],
        )

    def test_rollback_starts_all_three_old_function_apps(self):
        step = PauseOldFunctionApps(self.function_app_config)
        step.rollback()
        self.assertEqual(
            self.start_mock.call_args_list,
            [call(name, RESOURCE_GROUP, SUBSCRIPTION_ID) for name in self.function_app_config.control_plane.task_names],
        )


class TestUnpauseNewContainerAppJobs(EnablementTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.update_cron_mock = self.patch("azure_lfo_container_app_migration.enablement.update_container_app_job_cron_expression")

    def test_execute_sets_real_cron_on_all_three_new_jobs(self):
        step = UnpauseNewContainerAppJobs(self.caj_config)
        step.execute()

        self.assertEqual(
            self.update_cron_mock.call_args_list,
            [
                call(self.caj_config.control_plane.resources_task_name, RESOURCE_GROUP, SUBSCRIPTION_ID, RESOURCES_TASK_CRON),
                call(
                    self.caj_config.control_plane.diagnostic_settings_task_name,
                    RESOURCE_GROUP,
                    SUBSCRIPTION_ID,
                    DIAGNOSTIC_SETTINGS_TASK_CRON,
                ),
                call(self.caj_config.control_plane.scaling_task_name, RESOURCE_GROUP, SUBSCRIPTION_ID, SCALING_TASK_CRON),
            ],
        )

    def test_rollback_reverts_all_three_new_jobs_to_never_run_cron(self):
        step = UnpauseNewContainerAppJobs(self.caj_config)
        step.rollback()

        for c in self.update_cron_mock.call_args_list:
            self.assertEqual(c.args[3], NEVER_RUN_CRON_EXPRESSION)
        self.assertEqual(self.update_cron_mock.call_count, 3)


class TestUpdateDeployerImage(EnablementTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.update_image_mock = self.patch("azure_lfo_container_app_migration.enablement.update_container_app_job_image")

    def test_execute_sets_the_container_app_job_deployer_image(self):
        step = UpdateDeployerImage(self.caj_config, self.function_app_config)
        step.execute()
        self.update_image_mock.assert_called_once_with(
            self.caj_config.deployer_job_name, RESOURCE_GROUP, SUBSCRIPTION_ID, self.caj_config.deployer_image_url
        )

    def test_rollback_reverts_to_the_function_app_deployer_image(self):
        step = UpdateDeployerImage(self.caj_config, self.function_app_config)
        step.rollback()
        self.update_image_mock.assert_called_once_with(
            self.caj_config.deployer_job_name, RESOURCE_GROUP, SUBSCRIPTION_ID, self.function_app_config.deployer_image_url
        )


class TestUnpauseDeployer(EnablementTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.update_cron_mock = self.patch("azure_lfo_container_app_migration.enablement.update_container_app_job_cron_expression")

    def test_execute_restores_the_deployer_jobs_real_cron(self):
        step = UnpauseDeployer(self.caj_config)
        step.execute()
        self.update_cron_mock.assert_called_once_with(
            self.caj_config.deployer_job_name, RESOURCE_GROUP, SUBSCRIPTION_ID, DEPLOYER_TASK_CRON
        )

    def test_rollback_sets_the_deployer_job_to_never_run(self):
        step = UnpauseDeployer(self.caj_config)
        step.rollback()
        self.update_cron_mock.assert_called_once_with(
            self.caj_config.deployer_job_name, RESOURCE_GROUP, SUBSCRIPTION_ID, NEVER_RUN_CRON_EXPRESSION
        )
