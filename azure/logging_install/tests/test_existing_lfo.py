# stdlib
import json
from unittest import TestCase
from unittest.mock import patch as mock_patch

# project
from azure_logging_install.existing_lfo import check_existing_lfo, LfoMetadata
from azure_logging_install.configuration import Configuration

# Test data
MANAGEMENT_GROUP_ID = "test-mg"
CONTROL_PLANE_REGION = "eastus"
CONTROL_PLANE_SUBSCRIPTION = "test-sub-1"
CONTROL_PLANE_RESOURCE_GROUP = "test-rg"
MONITORED_SUBSCRIPTIONS = "sub-1,sub-2"
DATADOG_API_KEY = "test-api-key"
DATADOG_SITE = "datadoghq.com"
SUB_ID_TO_NAME = {
    "sub-1": "Test Subscription 1",
    "sub-2": "Test Subscription 2",
    "sub-3": "Test Subscription 3",
    "sub-4": "Test Subscription 4",
    CONTROL_PLANE_SUBSCRIPTION: "Test Control Plane Subscription",
}


class TestExistingLfo(TestCase):
    def setUp(self) -> None:
        """Set up test fixtures"""
        self.execute_mock = self.patch("azure_logging_install.existing_lfo.execute")

        # Create test configuration
        self.config = Configuration(
            management_group_id=MANAGEMENT_GROUP_ID,
            control_plane_region=CONTROL_PLANE_REGION,
            control_plane_sub_id=CONTROL_PLANE_SUBSCRIPTION,
            control_plane_rg=CONTROL_PLANE_RESOURCE_GROUP,
            monitored_subs=MONITORED_SUBSCRIPTIONS,
            datadog_api_key=DATADOG_API_KEY,
            datadog_site=DATADOG_SITE,
        )

    def patch(self, path: str, **kwargs):
        """Helper method to patch and auto-cleanup"""
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_check_existing_lfo_no_installations(self):
        """Test when no LFO installations exist"""
        self.execute_mock.return_value = "[]"

        result = check_existing_lfo(self.config.all_subscriptions, SUB_ID_TO_NAME)

        self.assertEqual(result, {})
        self.assertEqual(
            self.execute_mock.call_count, len(self.config.all_subscriptions)
        )

    def test_check_existing_lfo_single_installation(self):
        """Test with a single existing LFO installation"""
        mock_func_apps = [{"resourceGroup": "lfo-rg", "name": "resources-task-abc123"}]
        mock_monitored_subs_json = json.dumps(
            {
                "sub-1": SUB_ID_TO_NAME["sub-1"],
                "sub-2": SUB_ID_TO_NAME["sub-2"],
                "sub-3": SUB_ID_TO_NAME["sub-3"],
            }
        )

        self.execute_mock.side_effect = [
            json.dumps(mock_func_apps),  # functionapp list for first subscription
            mock_monitored_subs_json,  # appsettings for resources-task-abc123 (TSV returns raw JSON string)
            "[]",  # functionapp list for second subscription (empty)
            "[]",  # functionapp list for third subscription (empty)
        ]

        result = check_existing_lfo(self.config.all_subscriptions, SUB_ID_TO_NAME)

        self.assertEqual(len(result), 1)
        self.assertIn("abc123", result)

        lfo_metadata = result["abc123"]
        self.assertIsInstance(lfo_metadata, LfoMetadata)
        expected_monitored_subs = {
            "sub-1": SUB_ID_TO_NAME["sub-1"],
            "sub-2": SUB_ID_TO_NAME["sub-2"],
            "sub-3": SUB_ID_TO_NAME["sub-3"],
        }
        self.assertEqual(lfo_metadata.monitored_subs, expected_monitored_subs)
        self.assertIn(CONTROL_PLANE_SUBSCRIPTION, self.config.all_subscriptions)
        self.assertEqual(lfo_metadata.control_plane_rg, "lfo-rg")

    def test_check_existing_lfo_multiple_installations(self):
        """Test with multiple existing LFO installations"""
        mock_func_apps_sub1 = [
            {"resourceGroup": "lfo-rg-1", "name": "resources-task-def456"}
        ]

        mock_func_apps_sub2 = [
            {"resourceGroup": "lfo-rg-2", "name": "resources-task-ghi789"}
        ]

        mock_monitored_subs_1_json = json.dumps(
            {
                "sub-1": SUB_ID_TO_NAME["sub-1"],
                "sub-2": SUB_ID_TO_NAME["sub-2"],
            }
        )
        mock_monitored_subs_2_json = json.dumps(
            {
                "sub-3": SUB_ID_TO_NAME["sub-3"],
                "sub-4": SUB_ID_TO_NAME["sub-4"],
            }
        )

        self.execute_mock.side_effect = [
            json.dumps(mock_func_apps_sub1),  # functionapp list for first subscription
            mock_monitored_subs_1_json,  # appsettings for resources-task-def456 (TSV returns raw JSON string)
            json.dumps(mock_func_apps_sub2),  # functionapp list for second subscription
            mock_monitored_subs_2_json,  # appsettings for resources-task-ghi789 (TSV returns raw JSON string)
            "[]",  # functionapp list for third subscription (empty)
        ]

        result = check_existing_lfo(self.config.all_subscriptions, SUB_ID_TO_NAME)

        self.assertEqual(len(result), 2)
        self.assertIn("def456", result)
        self.assertIn("ghi789", result)

        lfo_1 = result["def456"]
        expected_lfo_1_subs = {
            "sub-1": SUB_ID_TO_NAME["sub-1"],
            "sub-2": SUB_ID_TO_NAME["sub-2"],
        }
        self.assertEqual(lfo_1.monitored_subs, expected_lfo_1_subs)
        self.assertEqual(lfo_1.control_plane_rg, "lfo-rg-1")

        lfo_2 = result["ghi789"]
        expected_lfo_2_subs = {
            "sub-3": SUB_ID_TO_NAME["sub-3"],
            "sub-4": SUB_ID_TO_NAME["sub-4"],
        }
        self.assertEqual(lfo_2.monitored_subs, expected_lfo_2_subs)
        self.assertEqual(lfo_2.control_plane_rg, "lfo-rg-2")
