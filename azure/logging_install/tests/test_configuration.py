# stdlib
import sys
import uuid
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch as mock_patch, MagicMock
import json

# Needed to import the src modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# project
from configuration import Configuration
from constants import NIL_UUID, STORAGE_ACCOUNT_KEY_FULL_PERMISSIONS
from errors import FatalError

# Test data
MANAGEMENT_GROUP_ID = "test-mg"
CONTROL_PLANE_REGION = "eastus"
CONTROL_PLANE_SUBSCRIPTION = "test-sub-1"
CONTROL_PLANE_RESOURCE_GROUP = "test-rg"
MONITORED_SUBSCRIPTIONS = "sub-1,sub-2,sub-3"
DATADOG_API_KEY = "test-api-key"
DATADOG_SITE = "datadoghq.com"
RESOURCE_TAG_FILTERS = "env:prod,team:infra"
PII_SCRUBBER_RULES = "rules:\n  - pattern: test"
TEST_STORAGE_KEY = "test-storage-key"


class TestConfiguration(TestCase):
    def setUp(self) -> None:
        """Set up test fixtures and reset global settings"""
        # Set up mocks
        self.log_mock = self.patch("configuration.log")
        self.execute_mock = self.patch("configuration.execute")

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

    # ===== Configuration Initialization Tests ===== #

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
        self.assertEqual(len(id1), 12)  # Should be 12 characters
        self.assertIsInstance(id1, str)

    def test_generate_control_plane_id_different_inputs(self):
        """Test control plane ID changes with different inputs"""
        config1 = self.create_test_config()
        config2 = self.create_test_config(management_group_id="different-mg")

        id1 = config1.generate_control_plane_id()
        id2 = config2.generate_control_plane_id()

        self.assertNotEqual(id1, id2)

    def test_generate_control_plane_id_format(self):
        """Test control plane ID format is correct"""
        config = self.create_test_config()
        control_plane_id = config.generate_control_plane_id()

        # Should be lowercase
        self.assertEqual(control_plane_id, control_plane_id.lower())
        # Should be alphanumeric (uuid format without hyphens in extracted portion)
        self.assertTrue(all(c.isalnum() for c in control_plane_id))

    @mock_patch("configuration.uuid.uuid5")
    def test_generate_control_plane_id_uses_uuid5(self, mock_uuid5):
        """Test control plane ID generation uses uuid5 with correct namespace"""
        mock_uuid5.return_value = uuid.UUID("12345678-9abc-def0-1234-56789abcdef0")
        config = self.create_test_config()

        # Generate a new ID since __post_init__ already called it once
        result = config.generate_control_plane_id()

        # Verify uuid5 was called (it gets called in __post_init__ and in our call)
        self.assertGreaterEqual(mock_uuid5.call_count, 1)
        call_args = mock_uuid5.call_args
        namespace_arg = call_args[0][0]
        self.assertEqual(str(namespace_arg), NIL_UUID)

        # Verify the result format (first 8 chars + next 4 chars after first hyphen)
        self.assertEqual(result, "12345678abcd")

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

        result = config.get_control_plane_cache_key()

        self.assertEqual(result, TEST_STORAGE_KEY)
        self.execute_mock.assert_not_called()

    def test_get_control_plane_cache_key_fetches_from_azure(self):
        """Test cache key fetches from Azure when not cached"""
        config = self.create_test_config()
        config.control_plane_cache_storage_key = None
        # Mock the execute to return a proper JSON response
        mock_keys_response = [{"keyName": "key1", "value": TEST_STORAGE_KEY}]
        self.execute_mock.return_value = json.dumps(mock_keys_response)

        result = config.get_control_plane_cache_key()

        self.assertEqual(result, TEST_STORAGE_KEY)
        self.assertEqual(config.control_plane_cache_storage_key, TEST_STORAGE_KEY)
        self.execute_mock.assert_called_once()

    def test_get_control_plane_cache_key_azure_command(self):
        """Test cache key uses correct Azure command"""
        config = self.create_test_config()
        config.control_plane_cache_storage_key = None
        # Mock the execute to return a proper JSON response
        mock_keys_response = [{"keyName": "key1", "value": TEST_STORAGE_KEY}]
        self.execute_mock.return_value = json.dumps(mock_keys_response)

        config.get_control_plane_cache_key()

        # Verify the AzCmd was called correctly
        call_args = self.execute_mock.call_args[0][0]
        cmd_str = call_args.str()
        self.assertIn("storage", cmd_str)
        self.assertIn("account", cmd_str)
        self.assertIn("keys", cmd_str)
        self.assertIn("list", cmd_str)
        self.assertIn(config.control_plane_cache_storage_name, cmd_str)
        self.assertIn(config.control_plane_rg, cmd_str)

    def test_get_control_plane_cache_key_handles_error(self):
        """Test cache key handles Azure CLI errors"""
        config = self.create_test_config()
        config.control_plane_cache_storage_key = None
        self.execute_mock.side_effect = FatalError("Storage account not found")

        with self.assertRaises(FatalError):
            config.get_control_plane_cache_key()

    # ===== Derived Property Tests ===== #

    def test_control_plane_cache_storage_name_property(self):
        """Test control_plane_cache_storage_name includes control plane ID"""
        config = self.create_test_config()

        # The control plane ID is generated in __post_init__, so we check the actual result
        result = config.control_plane_cache_storage_name

        self.assertTrue(result.startswith("lfostorage"))
        self.assertEqual(len(result), 19)  # "lfostorage" + 12 char ID

    def test_control_plane_env_name_property(self):
        """Test control_plane_env_name includes region and control plane ID"""
        config = self.create_test_config(control_plane_region="westus2")

        # The control plane ID is generated in __post_init__, so we check the actual result
        result = config.control_plane_env_name

        self.assertIn("westus2", result)
        self.assertTrue(result.startswith("dd-log-forwarder-env-"))

    def test_control_plane_job_name_property(self):
        """Test deployer_job_name format"""
        config = self.create_test_config()

        with mock_patch.object(
            config, "generate_control_plane_id", return_value="testid123456"
        ):
            result = config.deployer_job_name  # Use correct property name

        self.assertIn("testid123456", result)
        self.assertTrue(result.startswith("deployer-task-"))

    # ===== Method Tests ===== #

    def test_dataclass_behavior(self):
        """Test Configuration behaves as a proper dataclass"""
        config1 = self.create_test_config()
        config2 = self.create_test_config()
        config3 = self.create_test_config(datadog_site="datadoghq.eu")

        # Equal configs should be equal
        self.assertEqual(config1, config2)
        # Different configs should not be equal
        self.assertNotEqual(config1, config3)
        # Should have string representation
        self.assertIsInstance(str(config1), str)
        self.assertIn("Configuration", str(config1))
