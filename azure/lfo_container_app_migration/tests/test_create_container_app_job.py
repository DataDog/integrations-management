# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase
from unittest.mock import patch as mock_patch

from az_shared.errors import ResourceNotFoundError
from azure_logging_install.configuration import Configuration, ControlPlane, ControlPlaneType

from azure_lfo_container_app_migration.create_container_app_job import NEVER_RUN_CRON_EXPRESSION, CreateContainerAppJob

CONTROL_PLANE_ID = "abcdef123456"
SUBSCRIPTION_ID = "test-sub"
RESOURCE_GROUP = "test-rg"
REGION = "eastus"
JOB_NAME = "resources-task-abcdef123456"
IMAGE = "datadoghq.azurecr.io/resources-task:latest"


class TestCreateContainerAppJob(TestCase):
    def setUp(self) -> None:
        self.verify_mock = self.patch("azure_lfo_container_app_migration.create_container_app_job.verify_container_app_job_exists")
        self.query_env_vars_mock = self.patch("azure_lfo_container_app_migration.create_container_app_job.query_task_env_vars")
        self.create_job_mock = self.patch("azure_lfo_container_app_migration.create_container_app_job.create_container_app_job")
        self.delete_job_mock = self.patch("azure_lfo_container_app_migration.create_container_app_job.delete_container_app_job")

        self.config = Configuration(
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

    def test_skips_creation_if_job_already_exists(self):
        step = CreateContainerAppJob(self.config, JOB_NAME, IMAGE)

        step.execute()

        self.verify_mock.assert_called_once_with(JOB_NAME, RESOURCE_GROUP, SUBSCRIPTION_ID)
        self.query_env_vars_mock.assert_not_called()
        self.create_job_mock.assert_not_called()

    def test_creates_job_matching_existing_task_env_vars_with_unrunnable_cron_and_managed_identity(self):
        self.verify_mock.side_effect = ResourceNotFoundError("not found")
        self.query_env_vars_mock.return_value = {
            "DD_API_KEY": "test-api-key",
            "MONITORED_SUBSCRIPTIONS": '["sub-1"]',
        }

        step = CreateContainerAppJob(self.config, JOB_NAME, IMAGE)
        step.execute()

        self.query_env_vars_mock.assert_called_once_with(self.config.control_plane, JOB_NAME)
        self.create_job_mock.assert_called_once_with(
            job_name=JOB_NAME,
            resource_group=RESOURCE_GROUP,
            subscription_id=SUBSCRIPTION_ID,
            environment_name=self.config.control_plane_env_name,
            image=IMAGE,
            env_vars=["DD_API_KEY=test-api-key", "MONITORED_SUBSCRIPTIONS='[\"sub-1\"]'"],
            secrets=[],
            cron_expression=NEVER_RUN_CRON_EXPRESSION,
            timeout="300",
            retry_limit="0",
        )

    def test_rollback_deletes_job_only_if_it_was_created_by_this_step(self):
        self.verify_mock.side_effect = ResourceNotFoundError("not found")
        self.query_env_vars_mock.return_value = {}

        step = CreateContainerAppJob(self.config, JOB_NAME, IMAGE)
        step.execute()
        step.rollback()

        self.delete_job_mock.assert_called_once_with(JOB_NAME, RESOURCE_GROUP, SUBSCRIPTION_ID)

    def test_rollback_is_noop_if_job_already_existed(self):
        step = CreateContainerAppJob(self.config, JOB_NAME, IMAGE)
        step.execute()  # job already exists, nothing created
        step.rollback()

        self.delete_job_mock.assert_not_called()
