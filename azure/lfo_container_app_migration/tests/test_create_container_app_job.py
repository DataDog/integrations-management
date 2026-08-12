# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase
from unittest.mock import patch as mock_patch

from az_shared.errors import ResourceNotFoundError
from azure_logging_install.configuration import Configuration, ControlPlane, ControlPlaneType

from azure_lfo_container_app_migration.create_container_app_job import (
    NEVER_RUN_CRON_EXPRESSION,
    CreateContainerAppJob,
    CreateDiagnosticSettingsTaskContainerAppJob,
    CreateResourcesTaskContainerAppJob,
    CreateScalingTaskContainerAppJob,
)

CONTROL_PLANE_ID = "abcdef123456"
SUBSCRIPTION_ID = "test-sub"
RESOURCE_GROUP = "test-rg"
REGION = "eastus"
JOB_NAME = "some-job-name"


class RecordingCreateContainerAppJob(CreateContainerAppJob):
    """Concrete CreateContainerAppJob subclass that records create_job() calls, for testing the base class."""

    def __init__(self, config: Configuration, job_name: str, create_job_calls: list):
        super().__init__(config, job_name)
        self.create_job_calls = create_job_calls

    def create_job(self) -> None:
        self.create_job_calls.append(self.job_name)


class TestCreateContainerAppJob(TestCase):
    """Tests the shared base-class behavior (skip-if-exists, create, rollback)."""

    def setUp(self) -> None:
        self.verify_mock = self.patch("azure_lfo_container_app_migration.create_container_app_job.verify_container_app_job_exists")
        self.delete_job_mock = self.patch("azure_lfo_container_app_migration.create_container_app_job.delete_container_app_job")
        self.create_job_calls = []

        self.config = Configuration(
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

    def patch(self, path: str, **kwargs):
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def make_step(self) -> RecordingCreateContainerAppJob:
        return RecordingCreateContainerAppJob(self.config, JOB_NAME, self.create_job_calls)

    def test_skips_creation_if_job_already_exists(self):
        step = self.make_step()

        step.execute()

        self.verify_mock.assert_called_once_with(JOB_NAME, RESOURCE_GROUP, SUBSCRIPTION_ID)
        self.assertEqual(self.create_job_calls, [])

    def test_creates_job_if_it_does_not_exist(self):
        self.verify_mock.side_effect = ResourceNotFoundError("not found")

        step = self.make_step()
        step.execute()

        self.assertEqual(self.create_job_calls, [JOB_NAME])

    def test_rollback_deletes_job_only_if_it_was_created_by_this_step(self):
        self.verify_mock.side_effect = ResourceNotFoundError("not found")

        step = self.make_step()
        step.execute()
        step.rollback()

        self.delete_job_mock.assert_called_once_with(JOB_NAME, RESOURCE_GROUP, SUBSCRIPTION_ID)

    def test_rollback_is_noop_if_job_already_existed(self):
        step = self.make_step()
        step.execute()  # job already exists, nothing created
        step.rollback()

        self.delete_job_mock.assert_not_called()


class TestTaskSpecificSteps(TestCase):
    """Tests that each task-specific subclass wires up the right job name and resource_setup create function."""

    def setUp(self) -> None:
        self.verify_mock = self.patch("azure_lfo_container_app_migration.create_container_app_job.verify_container_app_job_exists")
        self.verify_mock.side_effect = ResourceNotFoundError("not found")

        self.config = Configuration(
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

    def patch(self, path: str, **kwargs):
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_resources_task_step(self):
        create_fn_mock = self.patch("azure_lfo_container_app_migration.create_container_app_job.create_resources_task_container_app_job")

        step = CreateResourcesTaskContainerAppJob(self.config)
        step.execute()

        self.verify_mock.assert_called_once_with(self.config.control_plane.resources_task_name, RESOURCE_GROUP, SUBSCRIPTION_ID)
        create_fn_mock.assert_called_once_with(self.config, NEVER_RUN_CRON_EXPRESSION)

    def test_diagnostic_settings_task_step(self):
        create_fn_mock = self.patch(
            "azure_lfo_container_app_migration.create_container_app_job.create_diagnostic_settings_task_container_app_job"
        )

        step = CreateDiagnosticSettingsTaskContainerAppJob(self.config)
        step.execute()

        self.verify_mock.assert_called_once_with(
            self.config.control_plane.diagnostic_settings_task_name, RESOURCE_GROUP, SUBSCRIPTION_ID
        )
        create_fn_mock.assert_called_once_with(self.config, NEVER_RUN_CRON_EXPRESSION)

    def test_scaling_task_step(self):
        create_fn_mock = self.patch("azure_lfo_container_app_migration.create_container_app_job.create_scaling_task_container_app_job")

        step = CreateScalingTaskContainerAppJob(self.config)
        step.execute()

        self.verify_mock.assert_called_once_with(self.config.control_plane.scaling_task_name, RESOURCE_GROUP, SUBSCRIPTION_ID)
        create_fn_mock.assert_called_once_with(self.config, NEVER_RUN_CRON_EXPRESSION)
