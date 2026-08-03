# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase
from unittest.mock import patch as mock_patch

from az_shared.errors import ResourceNotFoundError
from azure_caj_migration.container_jobs import (
    DIAGNOSTIC_SETTINGS,
    RESOURCES,
    build_container_job_steps,
    create_paused_task_job,
    get_task_specs,
    job_exists,
)

from caj_migration.tests.test_data import (
    CONTROL_PLANE_ENV_NAME,
    DIAGNOSTIC_SETTINGS_TASK_CONTAINER_APP_JOB_NAME,
    DIAGNOSTIC_SETTINGS_TASK_FUNCTION_APP_NAME,
    RESOURCES_TASK_NAME,
    SCALING_TASK_NAME,
    make_function_app_control_plane,
)


class TestGetTaskSpecs(TestCase):
    def test_resources_and_scaling_names_unchanged_diagnostic_settings_renamed(self):
        control_plane = make_function_app_control_plane()

        specs = {spec.key: spec for spec in get_task_specs(control_plane)}

        self.assertEqual(specs[RESOURCES].old_task_name, RESOURCES_TASK_NAME)
        self.assertEqual(specs[RESOURCES].new_task_name, RESOURCES_TASK_NAME)
        self.assertEqual(specs["scaling"].old_task_name, SCALING_TASK_NAME)
        self.assertEqual(specs["scaling"].new_task_name, SCALING_TASK_NAME)
        self.assertEqual(specs[DIAGNOSTIC_SETTINGS].old_task_name, DIAGNOSTIC_SETTINGS_TASK_FUNCTION_APP_NAME)
        self.assertEqual(specs[DIAGNOSTIC_SETTINGS].new_task_name, DIAGNOSTIC_SETTINGS_TASK_CONTAINER_APP_JOB_NAME)


class TestCreatePausedTaskJob(TestCase):
    def setUp(self) -> None:
        self.mock_execute = self.patch("azure_caj_migration.container_jobs.execute")
        self.mock_query_env_vars = self.patch("azure_caj_migration.container_jobs.query_task_env_vars")
        self.control_plane = make_function_app_control_plane()
        self.task = get_task_specs(self.control_plane)[0]

    def patch(self, path: str, **kwargs):
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_creates_job_when_it_does_not_exist(self):
        self.mock_execute.side_effect = [ResourceNotFoundError("not found"), "created"]
        self.mock_query_env_vars.return_value = {
            "AzureWebJobsStorage": "conn-str",
            "DD_API_KEY": "dd-key",
            "DD_SITE": "datadoghq.com",
        }

        result = create_paused_task_job(self.control_plane, CONTROL_PLANE_ENV_NAME, self.task)

        self.assertFalse(result.already_existed)
        self.assertEqual(self.mock_execute.call_count, 2)
        create_cmd = str(self.mock_execute.call_args_list[1].args[0])
        self.assertIn("job create", create_cmd)
        self.assertIn("--trigger-type Manual", create_cmd)

    def test_skips_creation_when_job_already_exists(self):
        self.mock_execute.return_value = "exists"

        result = job_exists(self.task.new_task_name, self.control_plane)
        self.assertTrue(result)

        self.mock_execute.reset_mock()
        result = create_paused_task_job(self.control_plane, CONTROL_PLANE_ENV_NAME, self.task)

        self.assertTrue(result.already_existed)
        self.mock_execute.assert_called_once()  # only the existence check, no create call
        self.mock_query_env_vars.assert_not_called()


class TestBuildContainerJobSteps(TestCase):
    def setUp(self) -> None:
        self.control_plane = make_function_app_control_plane()

    def test_rollback_only_deletes_jobs_created_this_run(self):
        created_jobs = {}
        with (
            mock_patch("azure_caj_migration.container_jobs.create_paused_task_job") as mock_create,
            mock_patch("azure_caj_migration.container_jobs.execute") as mock_execute,
        ):
            from azure_caj_migration.container_jobs import CreatedJob

            def fake_create(control_plane, env_name, task):
                already_existed = task.key != RESOURCES
                return CreatedJob(task=task, already_existed=already_existed)

            mock_create.side_effect = fake_create

            steps = build_container_job_steps(self.control_plane, CONTROL_PLANE_ENV_NAME, created_jobs)
            for step in steps:
                step.action()
            for step in steps:
                step.rollback()

            # Only the resources task job was newly created this run, so only it gets deleted.
            self.assertEqual(mock_execute.call_count, 1)
            deleted_cmd = str(mock_execute.call_args.args[0])
            self.assertIn("job delete", deleted_cmd)
            self.assertIn(RESOURCES_TASK_NAME, deleted_cmd)
