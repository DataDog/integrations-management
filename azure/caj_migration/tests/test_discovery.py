# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
from unittest import TestCase
from unittest.mock import patch as mock_patch

from az_shared.errors import FatalError, ResourceNotFoundError
from azure_caj_migration.discovery import (
    find_migration_candidates,
    get_monitored_subscription_ids,
    locate_deployer,
)
from azure_logging_install.configuration import ControlPlane, ControlPlaneType

from caj_migration.tests.test_data import (
    CONTROL_PLANE_ENV_NAME,
    CONTROL_PLANE_ID,
    CONTROL_PLANE_REGION,
    CONTROL_PLANE_SUBSCRIPTION_ID,
    DEPLOYER_JOB_NAME,
    RESOURCES_TASK_NAME,
    make_function_app_control_plane,
)


class TestFindMigrationCandidates(TestCase):
    def setUp(self) -> None:
        self.mock_find_existing = self.patch("azure_caj_migration.discovery.find_existing_lfo_control_planes")

    def patch(self, path: str, **kwargs):
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_filters_out_container_app_job_control_planes(self):
        func_app_cp = make_function_app_control_plane()
        caj_cp = ControlPlane(
            id="other123456",
            sub_id=CONTROL_PLANE_SUBSCRIPTION_ID,
            resource_group="other-rg",
            region=CONTROL_PLANE_REGION,
            type=ControlPlaneType.ContainerAppJobs,
        )
        self.mock_find_existing.return_value = [func_app_cp, caj_cp]

        result = find_migration_candidates()

        self.assertEqual(result, {CONTROL_PLANE_ID: func_app_cp})

    def test_explicit_ids_filter_further(self):
        func_app_cp = make_function_app_control_plane()
        other_cp = ControlPlane(
            id="other123456",
            sub_id=CONTROL_PLANE_SUBSCRIPTION_ID,
            resource_group="other-rg",
            region=CONTROL_PLANE_REGION,
            type=ControlPlaneType.FunctionApps,
        )
        self.mock_find_existing.return_value = [func_app_cp, other_cp]

        result = find_migration_candidates({CONTROL_PLANE_ID})

        self.assertEqual(result, {CONTROL_PLANE_ID: func_app_cp})

    def test_explicit_ids_not_found_are_dropped_with_a_warning(self):
        self.mock_find_existing.return_value = []

        result = find_migration_candidates({"missing-id"})

        self.assertEqual(result, {})


class TestLocateDeployer(TestCase):
    def setUp(self) -> None:
        self.execute_mock = self.patch("azure_caj_migration.discovery.execute")
        self.control_plane = make_function_app_control_plane()

    def patch(self, path: str, **kwargs):
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_returns_deployer_info_when_job_and_env_exist(self):
        self.execute_mock.side_effect = ["job details", "env details"]

        result = locate_deployer(self.control_plane)

        self.assertEqual(result.job_name, DEPLOYER_JOB_NAME)
        self.assertEqual(result.env_name, CONTROL_PLANE_ENV_NAME)

    def test_raises_fatal_error_when_deployer_job_missing(self):
        self.execute_mock.side_effect = ResourceNotFoundError("not found")

        with self.assertRaises(FatalError):
            locate_deployer(self.control_plane)

    def test_raises_fatal_error_when_environment_missing(self):
        self.execute_mock.side_effect = ["job details", ResourceNotFoundError("not found")]

        with self.assertRaises(FatalError):
            locate_deployer(self.control_plane)


class TestGetMonitoredSubscriptionIds(TestCase):
    def setUp(self) -> None:
        self.mock_query_env_vars = self.patch("azure_caj_migration.discovery.query_task_env_vars")
        self.control_plane = make_function_app_control_plane()

    def patch(self, path: str, **kwargs):
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_parses_monitored_subscriptions(self):
        self.mock_query_env_vars.return_value = {"MONITORED_SUBSCRIPTIONS": json.dumps(["sub-a", "sub-b"])}

        result = get_monitored_subscription_ids(self.control_plane)

        self.assertEqual(result, ["sub-a", "sub-b"])
        self.mock_query_env_vars.assert_called_once_with(self.control_plane, RESOURCES_TASK_NAME)

    def test_raises_fatal_error_when_missing(self):
        self.mock_query_env_vars.return_value = {}

        with self.assertRaises(FatalError):
            get_monitored_subscription_ids(self.control_plane)

    def test_raises_fatal_error_on_invalid_json(self):
        self.mock_query_env_vars.return_value = {"MONITORED_SUBSCRIPTIONS": "not-json"}

        with self.assertRaises(FatalError):
            get_monitored_subscription_ids(self.control_plane)
