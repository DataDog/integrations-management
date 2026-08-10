# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
from unittest import TestCase
from unittest.mock import patch as mock_patch

from az_shared.errors import FatalError, TimeoutError
from azure_lfo_container_app_migration.container_jobs import get_task_specs
from azure_lfo_container_app_migration.enablement import (
    build_enablement_steps,
    trigger_and_wait_for_job,
)
from azure_logging_install.constants import (
    DEPLOYER_IMAGE_FOR_CONTAINER_APP_JOBS,
    DEPLOYER_IMAGE_FOR_FUNCTION_APPS,
)

from caj_migration.tests.test_data import (
    DEPLOYER_JOB_NAME,
    RESOURCES_TASK_NAME,
    make_function_app_control_plane,
)


def _execution(status: str) -> str:
    return json.dumps({"properties": {"status": status}})


class TestTriggerAndWaitForJob(TestCase):
    def setUp(self) -> None:
        self.control_plane = make_function_app_control_plane()
        self.mock_execute = self.patch("azure_lfo_container_app_migration.enablement.execute")
        self.patch("azure_lfo_container_app_migration.enablement.sleep")

    def patch(self, path: str, **kwargs):
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_returns_on_success(self):
        self.mock_execute.side_effect = ["", _execution("Succeeded")]

        trigger_and_wait_for_job(RESOURCES_TASK_NAME, self.control_plane)

        self.assertEqual(self.mock_execute.call_count, 2)

    def test_raises_fatal_error_on_failed_status(self):
        self.mock_execute.side_effect = ["", _execution("Failed")]

        with self.assertRaises(FatalError):
            trigger_and_wait_for_job(RESOURCES_TASK_NAME, self.control_plane)

    def test_times_out_if_never_terminal(self):
        times = iter([0, 100, 200, 300, 400, 500, 600, 700, 800, 900])
        self.patch("azure_lfo_container_app_migration.enablement.time", side_effect=lambda: next(times))
        self.mock_execute.side_effect = [""] + [_execution("Running")] * 8

        with self.assertRaises(TimeoutError):
            trigger_and_wait_for_job(RESOURCES_TASK_NAME, self.control_plane)


class TestBuildEnablementSteps(TestCase):
    def setUp(self) -> None:
        self.control_plane = make_function_app_control_plane()
        self.task_specs = get_task_specs(self.control_plane)
        self.mock_stop_caj = self.patch("azure_lfo_container_app_migration.enablement.stop_container_app_job")
        self.mock_start_caj = self.patch("azure_lfo_container_app_migration.enablement.start_container_app_job")
        self.mock_stop_func = self.patch("azure_lfo_container_app_migration.enablement.stop_function_app")
        self.mock_start_func = self.patch("azure_lfo_container_app_migration.enablement.start_function_app")
        self.mock_trigger = self.patch("azure_lfo_container_app_migration.enablement.trigger_and_wait_for_job")
        self.mock_set_trigger = self.patch("azure_lfo_container_app_migration.enablement.set_job_trigger_type")
        self.mock_update_image = self.patch("azure_lfo_container_app_migration.enablement.update_container_app_job_image")

    def patch(self, path: str, **kwargs):
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_step_order_and_count(self):
        steps = build_enablement_steps(self.control_plane, DEPLOYER_JOB_NAME, self.task_specs)

        # pause deployer, pause 3 functions, trigger 3 jobs, unpause 3 jobs, update image, unpause deployer
        self.assertEqual(len(steps), 1 + 3 + 3 + 3 + 1 + 1)
        self.assertEqual(steps[0].name, "Pause deployer")
        self.assertEqual(steps[-1].name, "Unpause deployer")

    def test_pause_deployer_rollback_restarts_it(self):
        steps = build_enablement_steps(self.control_plane, DEPLOYER_JOB_NAME, self.task_specs)

        steps[0].action()
        self.mock_stop_caj.assert_called_once_with(DEPLOYER_JOB_NAME, self.control_plane)

        steps[0].rollback()
        self.mock_start_caj.assert_called_once_with(DEPLOYER_JOB_NAME, self.control_plane)

    def test_unpause_deployer_rollback_stops_it(self):
        steps = build_enablement_steps(self.control_plane, DEPLOYER_JOB_NAME, self.task_specs)

        steps[-1].action()
        self.mock_start_caj.assert_called_once_with(DEPLOYER_JOB_NAME, self.control_plane)

        steps[-1].rollback()
        self.mock_stop_caj.assert_called_once_with(DEPLOYER_JOB_NAME, self.control_plane)

    def test_pause_function_step_rollback_starts_the_same_function(self):
        steps = build_enablement_steps(self.control_plane, DEPLOYER_JOB_NAME, self.task_specs)
        pause_step = next(s for s in steps if s.name == f"Pause old Function App '{RESOURCES_TASK_NAME}'")

        pause_step.action()
        self.mock_stop_func.assert_called_once_with(RESOURCES_TASK_NAME, self.control_plane)

        pause_step.rollback()
        self.mock_start_func.assert_called_once_with(RESOURCES_TASK_NAME, self.control_plane)

    def test_trigger_step_has_no_rollback(self):
        steps = build_enablement_steps(self.control_plane, DEPLOYER_JOB_NAME, self.task_specs)
        trigger_step = next(s for s in steps if s.name.startswith("Trigger and verify"))

        # default no-op rollback should not raise or call any mocked function.
        trigger_step.rollback()
        self.mock_trigger.assert_not_called()

    def test_unpause_job_rollback_reverts_to_manual_trigger(self):
        steps = build_enablement_steps(self.control_plane, DEPLOYER_JOB_NAME, self.task_specs)
        unpause_step = next(s for s in steps if s.name.startswith("Unpause new"))

        unpause_step.action()
        self.assertEqual(self.mock_set_trigger.call_args.args[2], "Schedule")

        unpause_step.rollback()
        self.assertEqual(self.mock_set_trigger.call_args.args[2], "Manual")
        self.assertIsNone(self.mock_set_trigger.call_args.args[3])

    def test_update_image_step_rollback_reverts_to_function_app_image(self):
        steps = build_enablement_steps(self.control_plane, DEPLOYER_JOB_NAME, self.task_specs)
        image_step = next(s for s in steps if s.name == "Update deployer image to Container App Job-aware image")

        image_step.action()
        self.assertIn(DEPLOYER_IMAGE_FOR_CONTAINER_APP_JOBS, self.mock_update_image.call_args.args[2])

        image_step.rollback()
        self.assertIn(DEPLOYER_IMAGE_FOR_FUNCTION_APPS, self.mock_update_image.call_args.args[2])
