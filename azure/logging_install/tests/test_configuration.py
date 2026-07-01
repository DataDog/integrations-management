# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
from unittest import TestCase
from unittest.mock import patch as mock_patch

from az_shared.errors import FatalError
from azure_logging_install.configuration import (
    Configuration,
    ControlPlane,
    ControlPlaneType,
    generate_control_plane_id,
)

from logging_install.tests.test_data import (
    CONTROL_PLANE_ID,
    CONTROL_PLANE_REGION,
    CONTROL_PLANE_RESOURCE_GROUP,
    CONTROL_PLANE_SUBSCRIPTION_ID,
    DATADOG_API_KEY,
    DATADOG_SITE,
    MONITORED_SUBSCRIPTIONS,
    PII_SCRUBBER_RULES,
    RESOURCE_TAG_FILTERS,
    SUB_1_ID,
    TEST_STORAGE_KEY,
    make_control_plane,
)

CONTROL_PLANE_ID_LENGTH = 12
LFO_STORAGE_PREFIX = "lfostorage"
LOG_FORWARDER_ENV_PREFIX = "dd-log-forwarder-env-"
DEPLOYER_JOB_PREFIX = "deployer-task-"


class TestControlPlaneType(TestCase):
    def test_values(self):
        """Test ControlPlaneType enum values"""
        self.assertEqual(ControlPlaneType.FunctionApps, 1)
        self.assertEqual(ControlPlaneType.ContainerAppJobs, 2)


class TestGenerateControlPlaneId(TestCase):
    def test_generate_control_plane_id_deterministic(self):
        """Test control plane ID generation is deterministic"""
        id1 = generate_control_plane_id(CONTROL_PLANE_SUBSCRIPTION_ID, CONTROL_PLANE_RESOURCE_GROUP, CONTROL_PLANE_REGION)
        id2 = generate_control_plane_id(CONTROL_PLANE_SUBSCRIPTION_ID, CONTROL_PLANE_RESOURCE_GROUP, CONTROL_PLANE_REGION)

        self.assertEqual(id1, id2)
        self.assertEqual(len(id1), CONTROL_PLANE_ID_LENGTH)
        self.assertIsInstance(id1, str)

    def test_generate_control_plane_id_different_inputs(self):
        """Test control plane ID changes with different inputs"""
        id1 = generate_control_plane_id(CONTROL_PLANE_SUBSCRIPTION_ID, CONTROL_PLANE_RESOURCE_GROUP, CONTROL_PLANE_REGION)
        id2 = generate_control_plane_id(CONTROL_PLANE_SUBSCRIPTION_ID, "different-rg", CONTROL_PLANE_REGION)

        self.assertNotEqual(id1, id2)


class TestControlPlane(TestCase):
    def setUp(self) -> None:
        """Set up test fixtures and reset global settings"""
        self.az_cmd_execute_mock = self.patch("azure_logging_install.configuration.execute")
        self.az_cmd_execute_mock.return_value = json.dumps(
            [{"keyName": "key1", "value": TEST_STORAGE_KEY, "permissions": "FULL"}]
        )

    def patch(self, path: str, **kwargs):
        """Helper method to patch and auto-cleanup"""
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    # ===== Cache Key Fetch Tests ===== #

    def test_cache_key_fetched_from_azure_on_construction(self):
        """Test cache key is fetched from Azure eagerly during construction"""
        mock_keys_response = [{"keyName": "key1", "value": TEST_STORAGE_KEY, "permissions": "FULL"}]
        self.az_cmd_execute_mock.return_value = json.dumps(mock_keys_response)

        control_plane = ControlPlane(
            id=CONTROL_PLANE_ID,
            region=CONTROL_PLANE_REGION,
            subscription_id=CONTROL_PLANE_SUBSCRIPTION_ID,
            resource_group=CONTROL_PLANE_RESOURCE_GROUP,
        )

        self.assertEqual(control_plane.cache_storage_key, TEST_STORAGE_KEY)
        self.az_cmd_execute_mock.assert_called_once()

    def test_cache_key_fetch_no_full_permission_key_raises(self):
        """Test cache key fetch raises FatalError when no key has full permissions"""
        mock_keys_response = [{"keyName": "key1", "value": "some-key", "permissions": "READ"}]
        self.az_cmd_execute_mock.return_value = json.dumps(mock_keys_response)

        with self.assertRaises(FatalError):
            ControlPlane(
                id=CONTROL_PLANE_ID,
                region=CONTROL_PLANE_REGION,
                subscription_id=CONTROL_PLANE_SUBSCRIPTION_ID,
                resource_group=CONTROL_PLANE_RESOURCE_GROUP,
            )

    def test_cache_key_fetch_empty_list_raises(self):
        """Test cache key fetch raises FatalError when Azure returns an empty list"""
        self.az_cmd_execute_mock.return_value = json.dumps([])

        with self.assertRaises(FatalError):
            ControlPlane(
                id=CONTROL_PLANE_ID,
                region=CONTROL_PLANE_REGION,
                subscription_id=CONTROL_PLANE_SUBSCRIPTION_ID,
                resource_group=CONTROL_PLANE_RESOURCE_GROUP,
            )

    def test_cache_key_fetch_invalid_json_raises(self):
        """Test cache key fetch raises FatalError on invalid JSON"""
        self.az_cmd_execute_mock.return_value = "not json"

        with self.assertRaises(FatalError):
            ControlPlane(
                id=CONTROL_PLANE_ID,
                region=CONTROL_PLANE_REGION,
                subscription_id=CONTROL_PLANE_SUBSCRIPTION_ID,
                resource_group=CONTROL_PLANE_RESOURCE_GROUP,
            )

    # ===== Derived Attribute Tests ===== #

    def test_cache_storage_name(self):
        """Test cache_storage_name includes control plane ID"""
        control_plane = make_control_plane(id=CONTROL_PLANE_ID)

        self.assertEqual(control_plane.cache_storage_name, f"lfostorage{CONTROL_PLANE_ID}")

    def test_cache_storage_url(self):
        """Test cache_storage_url is derived from cache_storage_name"""
        control_plane = make_control_plane(id=CONTROL_PLANE_ID)

        self.assertEqual(
            control_plane.cache_storage_url,
            f"https://lfostorage{CONTROL_PLANE_ID}.blob.core.windows.net",
        )

    def test_cache_conn_string(self):
        """Test cache_conn_string contains storage name and key"""
        control_plane = make_control_plane(id=CONTROL_PLANE_ID)

        self.assertIn(f"lfostorage{CONTROL_PLANE_ID}", control_plane.cache_conn_string)
        self.assertIn(TEST_STORAGE_KEY, control_plane.cache_conn_string)

    def test_sub_scope_and_rg_scope(self):
        """Test sub_scope and rg_scope are derived from subscription/resource group"""
        control_plane = make_control_plane(
            subscription_id=CONTROL_PLANE_SUBSCRIPTION_ID, resource_group=CONTROL_PLANE_RESOURCE_GROUP
        )

        self.assertEqual(control_plane.sub_scope, f"/subscriptions/{CONTROL_PLANE_SUBSCRIPTION_ID}")
        self.assertEqual(
            control_plane.rg_scope,
            f"/subscriptions/{CONTROL_PLANE_SUBSCRIPTION_ID}/resourceGroups/{CONTROL_PLANE_RESOURCE_GROUP}",
        )

    def test_container_app_env_name(self):
        """Test container_app_env_name includes region and control plane ID"""
        control_plane = make_control_plane(id=CONTROL_PLANE_ID, region="westus2")

        self.assertEqual(control_plane.container_app_env_name, f"dd-log-forwarder-env-{CONTROL_PLANE_ID}-westus2")

    def test_deployer_job_name(self):
        """Test deployer_job_name format"""
        control_plane = make_control_plane(id=CONTROL_PLANE_ID)

        self.assertEqual(control_plane.deployer_job_name, f"deployer-task-{CONTROL_PLANE_ID}")

    def test_container_app_start_role_name(self):
        """Test container_app_start_role_name includes control plane ID"""
        control_plane = make_control_plane(id=CONTROL_PLANE_ID)

        self.assertEqual(control_plane.container_app_start_role_name, f"ContainerAppStartRole{CONTROL_PLANE_ID}")

    def test_task_names_function_apps(self):
        """Test task names for FunctionApps control plane type"""
        control_plane = make_control_plane(id=CONTROL_PLANE_ID, type=ControlPlaneType.FunctionApps)

        self.assertEqual(control_plane.resources_task_name, f"resources-task-{CONTROL_PLANE_ID}")
        self.assertEqual(control_plane.scaling_task_name, f"scaling-task-{CONTROL_PLANE_ID}")
        self.assertEqual(control_plane.diagnostic_settings_task_name, f"diagnostic-settings-task-{CONTROL_PLANE_ID}")
        self.assertEqual(
            control_plane.task_names,
            [
                f"resources-task-{CONTROL_PLANE_ID}",
                f"scaling-task-{CONTROL_PLANE_ID}",
                f"diagnostic-settings-task-{CONTROL_PLANE_ID}",
            ],
        )

    def test_task_names_container_app_jobs(self):
        """Test diagnostic settings task name differs for ContainerAppJobs control plane type"""
        control_plane = make_control_plane(id=CONTROL_PLANE_ID, type=ControlPlaneType.ContainerAppJobs)

        self.assertEqual(control_plane.diagnostic_settings_task_name, f"diag-settings-task-{CONTROL_PLANE_ID}")

    def test_deployer_image_url_function_apps(self):
        """Test deployer image url for FunctionApps control plane type"""
        control_plane = make_control_plane(type=ControlPlaneType.FunctionApps)

        self.assertEqual(control_plane.deployer_image_url, "datadoghq.azurecr.io/deployer:latest")

    def test_deployer_image_url_container_app_jobs(self):
        """Test deployer image url for ContainerAppJobs control plane type"""
        control_plane = make_control_plane(type=ControlPlaneType.ContainerAppJobs)

        self.assertEqual(control_plane.deployer_image_url, "datadoghq.azurecr.io/deployer-caj:latest")

    def test_default_type_is_function_apps(self):
        """Test ControlPlane defaults to FunctionApps type"""
        control_plane = make_control_plane()

        self.assertEqual(control_plane.type, ControlPlaneType.FunctionApps)


class TestConfiguration(TestCase):
    def setUp(self) -> None:
        self.az_cmd_execute_mock = self.patch("azure_logging_install.configuration.execute")
        self.az_cmd_execute_mock.return_value = json.dumps(
            [{"keyName": "key1", "value": TEST_STORAGE_KEY, "permissions": "FULL"}]
        )

    def patch(self, path: str, **kwargs):
        """Helper method to patch and auto-cleanup"""
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_configuration_initialization_with_defaults(self):
        """Test Configuration initialization with default values"""
        control_plane = make_control_plane()
        config = Configuration(
            control_plane=control_plane,
            monitored_subs=MONITORED_SUBSCRIPTIONS,
            datadog_api_key=DATADOG_API_KEY,
        )

        # Required fields
        self.assertIs(config.control_plane, control_plane)
        self.assertEqual(config.monitored_subscriptions, MONITORED_SUBSCRIPTIONS)
        self.assertEqual(config.datadog_api_key, DATADOG_API_KEY)

        # Default values
        self.assertEqual(config.datadog_site, "datadoghq.com")
        self.assertEqual(config.resource_tag_filters, "")
        self.assertEqual(config.pii_scrubber_rules, "")
        self.assertFalse(config.datadog_telemetry)
        self.assertEqual(config.log_level, "INFO")

    def test_configuration_initialization_with_custom_values(self):
        """Test Configuration initialization with custom values"""
        control_plane = make_control_plane()
        config = Configuration(
            control_plane=control_plane,
            monitored_subs=MONITORED_SUBSCRIPTIONS,
            datadog_api_key=DATADOG_API_KEY,
            datadog_site="datadoghq.eu",
            resource_tag_filters=RESOURCE_TAG_FILTERS,
            pii_scrubber_rules=PII_SCRUBBER_RULES,
            datadog_telemetry=True,
            log_level="DEBUG",
        )

        self.assertEqual(config.datadog_site, "datadoghq.eu")
        self.assertEqual(config.resource_tag_filters, RESOURCE_TAG_FILTERS)
        self.assertEqual(config.pii_scrubber_rules, PII_SCRUBBER_RULES)
        self.assertTrue(config.datadog_telemetry)
        self.assertEqual(config.log_level, "DEBUG")

    def test_monitored_subscriptions_passed_through(self):
        """Test monitored_subscriptions is the list passed in, unmodified"""
        control_plane = make_control_plane()
        monitored_subs = [SUB_1_ID]
        config = Configuration(
            control_plane=control_plane,
            monitored_subs=monitored_subs,
            datadog_api_key=DATADOG_API_KEY,
        )

        self.assertEqual(config.monitored_subscriptions, monitored_subs)

    def test_all_subscriptions_includes_control_plane_and_monitored(self):
        """Test all_subscriptions property includes control plane + monitored subs"""
        control_plane = make_control_plane(subscription_id="control-sub")
        config = Configuration(
            control_plane=control_plane,
            monitored_subs=["mon1", "mon2"],
            datadog_api_key=DATADOG_API_KEY,
        )

        self.assertEqual(config.all_subscriptions, {"control-sub", "mon1", "mon2"})

    def test_all_subscriptions_no_duplicates(self):
        """Test all_subscriptions property removes duplicates (it's a set)"""
        control_plane = make_control_plane(subscription_id="same-sub")
        config = Configuration(
            control_plane=control_plane,
            monitored_subs=["same-sub", "other-sub"],
            datadog_api_key=DATADOG_API_KEY,
        )

        self.assertEqual(config.all_subscriptions, {"same-sub", "other-sub"})
