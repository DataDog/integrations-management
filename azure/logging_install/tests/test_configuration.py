# stdlib
import json
from unittest import TestCase
from unittest.mock import patch as mock_patch, MagicMock

# project
from azure_logging_install.configuration import Configuration

# Test data
CONTROL_PLANE_ID_LENGTH = 12
LFO_STORAGE_PREFIX = "lfostorage"
LOG_FORWARDER_ENV_PREFIX = "dd-log-forwarder-env-"
DEPLOYER_JOB_PREFIX = "deployer-task-"

MANAGEMENT_GROUP_ID = "test-mg"
CONTROL_PLANE_REGION = "eastus"
CONTROL_PLANE_SUBSCRIPTION = "test-sub-1"
CONTROL_PLANE_RESOURCE_GROUP = "test-rg"
MONITORED_SUBSCRIPTIONS = "sub-1,sub-2,sub-3"
DATADOG_API_KEY = "test-api-key"
DATADOG_SITE = "datadoghq.com"
RESOURCE_TAG_FILTERS = "env:prod,team:infra"
PII_SCRUBBER_RULES = "rule1:\n  - pattern: test"
TEST_STORAGE_KEY = "test-storage-key"


class TestConfiguration(TestCase):
    def setUp(self) -> None:
        """Set up test fixtures and reset global settings"""
        # Set up mocks
        self.az_cmd_execute_mock = self.patch(
            "azure_logging_install.configuration.execute"
        )

    def patch(self, path: str, **kwargs):
        """Helper method to patch and auto-cleanup"""
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def create_test_config(self, **overrides):
        """Helper to create a test configuration with optional overrides"""
        defaults = {
            "management_group_id": MANAGEMENT_GROUP_ID,
            "control_plane_region": CONTROL_PLANE_REGION,
            "control_plane_sub_id": CONTROL_PLANE_SUBSCRIPTION,
            "control_plane_rg": CONTROL_PLANE_RESOURCE_GROUP,
            "monitored_subs": MONITORED_SUBSCRIPTIONS,
            "datadog_api_key": DATADOG_API_KEY,
            "datadog_site": DATADOG_SITE,
            "resource_tag_filters": RESOURCE_TAG_FILTERS,
            "pii_scrubber_rules": PII_SCRUBBER_RULES,
            "datadog_telemetry": False,
            "log_level": "INFO",
        }
        defaults.update(overrides)
        return Configuration(**defaults)

    def test_configuration_initialization_with_defaults(self):
        """Test Configuration initialization with default values"""
        config = Configuration(
            management_group_id=MANAGEMENT_GROUP_ID,
            control_plane_region=CONTROL_PLANE_REGION,
            control_plane_sub_id=CONTROL_PLANE_SUBSCRIPTION,
            control_plane_rg=CONTROL_PLANE_RESOURCE_GROUP,
            monitored_subs=MONITORED_SUBSCRIPTIONS,
            datadog_api_key=DATADOG_API_KEY,
        )

        # Required fields
        self.assertEqual(config.management_group_id, MANAGEMENT_GROUP_ID)
        self.assertEqual(config.control_plane_region, CONTROL_PLANE_REGION)
        self.assertEqual(config.control_plane_sub_id, CONTROL_PLANE_SUBSCRIPTION)
        self.assertEqual(config.control_plane_rg, CONTROL_PLANE_RESOURCE_GROUP)
        self.assertEqual(config.monitored_subs, MONITORED_SUBSCRIPTIONS)
        self.assertEqual(config.datadog_api_key, DATADOG_API_KEY)

        # Default values
        self.assertEqual(config.datadog_site, "datadoghq.com")
        self.assertEqual(config.resource_tag_filters, "")
        self.assertEqual(config.pii_scrubber_rules, "")
        self.assertFalse(config.datadog_telemetry)
        self.assertEqual(config.log_level, "INFO")

    def test_configuration_initialization_with_custom_values(self):
        """Test Configuration initialization with custom values"""
        config = self.create_test_config(
            datadog_site="datadoghq.eu", datadog_telemetry=True, log_level="DEBUG"
        )

        self.assertEqual(config.datadog_site, "datadoghq.eu")
        self.assertEqual(config.resource_tag_filters, RESOURCE_TAG_FILTERS)
        self.assertEqual(config.pii_scrubber_rules, PII_SCRUBBER_RULES)
        self.assertTrue(config.datadog_telemetry)
        self.assertEqual(config.log_level, "DEBUG")

    # ===== Control Plane ID Generation Tests ===== #

    def test_generate_control_plane_id_deterministic(self):
        """Test control plane ID generation is deterministic"""
        config1 = self.create_test_config()
        config2 = self.create_test_config()

        id1 = config1.generate_control_plane_id()
        id2 = config2.generate_control_plane_id()

        self.assertEqual(id1, id2)
        self.assertEqual(len(id1), CONTROL_PLANE_ID_LENGTH)
        self.assertIsInstance(id1, str)

    def test_generate_control_plane_id_different_inputs(self):
        """Test control plane ID changes with different inputs"""
        config1 = self.create_test_config()
        config2 = self.create_test_config(management_group_id="different-mg")

        id1 = config1.generate_control_plane_id()
        id2 = config2.generate_control_plane_id()

        self.assertNotEqual(id1, id2)

    # ===== Property Tests ===== #

    def test_monitored_subscriptions_property(self):
        """Test monitored_subscriptions property splits comma-separated values"""
        config = self.create_test_config(monitored_subs="sub1,sub2,sub3")

        result = config.monitored_subscriptions

        self.assertEqual(result, ["sub1", "sub2", "sub3"])

    def test_monitored_subscriptions_property_single_sub(self):
        """Test monitored_subscriptions property with single subscription"""
        config = self.create_test_config(monitored_subs="single-sub")

        result = config.monitored_subscriptions

        self.assertEqual(result, ["single-sub"])

    def test_monitored_subscriptions_property_with_spaces(self):
        """Test monitored_subscriptions property strips whitespace"""
        config = self.create_test_config(monitored_subs=" sub1 , sub2 , sub3 ")

        result = config.monitored_subscriptions

        self.assertEqual(result, ["sub1", "sub2", "sub3"])

    def test_all_subscriptions_property(self):
        """Test all_subscriptions property includes control plane + monitored"""
        config = self.create_test_config(
            control_plane_sub_id="control-sub", monitored_subs="mon1,mon2"
        )

        result = config.all_subscriptions

        expected = ["control-sub", "mon1", "mon2"]
        self.assertEqual(sorted(result), sorted(expected))

    def test_all_subscriptions_property_no_duplicates(self):
        """Test all_subscriptions property removes duplicates"""
        config = self.create_test_config(
            control_plane_sub_id="same-sub", monitored_subs="same-sub,other-sub"
        )

        result = config.all_subscriptions

        expected = ["same-sub", "other-sub"]
        self.assertEqual(sorted(result), sorted(expected))

    # ===== Storage Account Cache Key Tests ===== #

    def test_get_control_plane_cache_key_cached(self):
        """Test cache key returns cached value if available"""
        config = self.create_test_config()
        config.control_plane_cache_storage_key = TEST_STORAGE_KEY

        self.assertEqual(config.get_control_plane_cache_key(), TEST_STORAGE_KEY)
        self.az_cmd_execute_mock.assert_not_called()

    def test_get_control_plane_cache_key_fetches_from_azure(self):
        """Test cache key fetches from Azure when not cached"""
        config = self.create_test_config()
        config.control_plane_cache_storage_key = None
        # Mock the execute to return a proper JSON response with valid permissions
        mock_keys_response = [
            {"keyName": "key1", "value": TEST_STORAGE_KEY, "permissions": "FULL"}
        ]
        self.az_cmd_execute_mock.return_value = json.dumps(mock_keys_response)

        result = config.get_control_plane_cache_key()

        self.assertEqual(result, TEST_STORAGE_KEY)
        self.assertEqual(config.control_plane_cache_storage_key, TEST_STORAGE_KEY)
        self.az_cmd_execute_mock.assert_called_once()

    # ===== Derived Property Tests ===== #

    def test_control_plane_cache_storage_name_property(self):
        """Test control_plane_cache_storage_name includes control plane ID"""
        config = self.create_test_config()

        self.assertTrue(
            config.control_plane_cache_storage_name.startswith(LFO_STORAGE_PREFIX)
        )
        self.assertEqual(
            len(config.control_plane_cache_storage_name),
            len(LFO_STORAGE_PREFIX) + CONTROL_PLANE_ID_LENGTH,
        )

    def test_control_plane_env_name_property(self):
        """Test control_plane_env_name includes region and control plane ID"""
        config = self.create_test_config(control_plane_region="westus2")

        self.assertIn("westus2", config.control_plane_env_name)
        self.assertTrue(
            config.control_plane_env_name.startswith(LOG_FORWARDER_ENV_PREFIX)
        )
        self.assertEqual(
            len(config.control_plane_env_name),
            len(LOG_FORWARDER_ENV_PREFIX) + len("westus2-") + CONTROL_PLANE_ID_LENGTH,
        )

    def test_control_plane_job_name_property(self):
        """Test deployer_job_name format"""
        config = self.create_test_config()

        self.assertTrue(config.deployer_job_name.startswith(DEPLOYER_JOB_PREFIX))
        self.assertEqual(
            len(config.deployer_job_name),
            len(DEPLOYER_JOB_PREFIX) + CONTROL_PLANE_ID_LENGTH,
        )
