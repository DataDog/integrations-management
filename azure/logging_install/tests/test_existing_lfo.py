# stdlib
import json
from unittest import TestCase
from unittest.mock import patch as mock_patch

# project
from azure_logging_install.existing_lfo import (
    check_existing_lfo,
    LfoMetadata,
    MONITORED_SUBSCRIPTIONS_KEY,
    RESOURCE_TAG_FILTERS_KEY,
    PII_SCRUBBER_RULES_KEY,
)
from azure_logging_install.configuration import Configuration

from tests.test_data import (
    CONTROL_PLANE_REGION,
    CONTROL_PLANE_SUBSCRIPTION_ID,
    CONTROL_PLANE_RESOURCE_GROUP,
    MONITORED_SUBSCRIPTIONS,
    DATADOG_API_KEY,
    DATADOG_SITE,
    SUB_ID_TO_NAME,
    SUB_1_ID,
    SUB_2_ID,
    SUB_3_ID,
    SUB_4_ID,
    RESOURCE_TAG_FILTERS,
    PII_SCRUBBER_RULES,
)


class TestExistingLfo(TestCase):
    def setUp(self) -> None:
        """Set up test fixtures"""
        self.execute_mock = self.patch("azure_logging_install.existing_lfo.execute")

        # Create test configuration
        self.config = Configuration(
            control_plane_region=CONTROL_PLANE_REGION,
            control_plane_sub_id=CONTROL_PLANE_SUBSCRIPTION_ID,
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

    def make_execute_router(
        self,
        func_apps_json: str,
        func_apps_settings: dict[str, dict[str, str]] = {},
    ):
        def _router(az_cmd, can_fail=False):
            cmd = az_cmd.str()
            if "extension show" in cmd:
                return "installed"
            if "graph query" in cmd:
                return func_apps_json
            if "config appsettings list" in cmd:
                resource_task_name = cmd.split("--name")[1].split()[0]

                # Return env vars for this function app as a JSON list, like the az cli
                env_vars = func_apps_settings.get(resource_task_name, {})
                return json.dumps(
                    [{"name": key, "value": value} for key, value in env_vars.items()]
                )
            raise AssertionError(f"Unexpected az cmd: {cmd}")

        return _router

    def test_check_existing_lfo_no_installations(self):
        """Test when no LFO installations exist"""
        self.execute_mock.side_effect = self.make_execute_router(
            json.dumps({"data": []}),  # graph query returns empty data
        )

        result = check_existing_lfo(self.config.all_subscriptions, SUB_ID_TO_NAME)

        self.assertEqual(result, {})
        self.assertEqual(self.execute_mock.call_count, 2)

    def test_check_existing_lfo_single_installation(self):
        """Test with a single existing LFO installation"""
        mock_func_apps = {
            "data": [
                {
                    "resourceGroup": "lfo-rg",
                    "name": "resources-task-abc123",
                    "location": "eastus",
                    "subscriptionId": SUB_1_ID,
                }
            ]
        }
        mock_monitored_subs_json = json.dumps(
            {
                SUB_1_ID: SUB_ID_TO_NAME[SUB_1_ID],
                SUB_2_ID: SUB_ID_TO_NAME[SUB_2_ID],
                SUB_3_ID: SUB_ID_TO_NAME[SUB_3_ID],
            }
        )

        self.execute_mock.side_effect = self.make_execute_router(
            json.dumps(mock_func_apps),  # graph query for function apps
            {
                "resources-task-abc123": {
                    MONITORED_SUBSCRIPTIONS_KEY: mock_monitored_subs_json,
                    RESOURCE_TAG_FILTERS_KEY: RESOURCE_TAG_FILTERS,
                    PII_SCRUBBER_RULES_KEY: PII_SCRUBBER_RULES,
                }
            },
        )

        result = check_existing_lfo(self.config.all_subscriptions, SUB_ID_TO_NAME)

        self.assertEqual(len(result), 1)
        self.assertIn("abc123", result)

        lfo_metadata = result["abc123"]
        self.assertIsInstance(lfo_metadata, LfoMetadata)
        expected_monitored_subs = {
            SUB_1_ID: SUB_ID_TO_NAME[SUB_1_ID],
            SUB_2_ID: SUB_ID_TO_NAME[SUB_2_ID],
            SUB_3_ID: SUB_ID_TO_NAME[SUB_3_ID],
        }
        self.assertIn(CONTROL_PLANE_SUBSCRIPTION_ID, self.config.all_subscriptions)
        self.assertEqual(lfo_metadata.control_plane.resource_group, "lfo-rg")
        self.assertEqual(lfo_metadata.monitored_subs, expected_monitored_subs)
        self.assertEqual(lfo_metadata.tag_filter, RESOURCE_TAG_FILTERS)
        self.assertEqual(lfo_metadata.pii_rules, PII_SCRUBBER_RULES)

    def test_check_existing_lfo_multiple_installations(self):
        """Test with multiple existing LFO installations"""
        mock_func_apps = {
            "data": [
                {
                    "resourceGroup": "lfo-rg-1",
                    "name": "resources-task-def456",
                    "location": "eastus",
                    "subscriptionId": SUB_1_ID,
                },
                {
                    "resourceGroup": "lfo-rg-2",
                    "name": "resources-task-ghi789",
                    "location": "eastus",
                    "subscriptionId": SUB_2_ID,
                },
            ],
        }
        mock_monitored_subs_1_json = json.dumps(
            {
                SUB_1_ID: SUB_ID_TO_NAME[SUB_1_ID],
                SUB_2_ID: SUB_ID_TO_NAME[SUB_2_ID],
            }
        )
        mock_monitored_subs_2_json = json.dumps(
            {
                SUB_3_ID: SUB_ID_TO_NAME[SUB_3_ID],
                SUB_4_ID: SUB_ID_TO_NAME[SUB_4_ID],
            }
        )
        mock_resource_tag_filters = RESOURCE_TAG_FILTERS
        mock_pii_scrubber_rules = PII_SCRUBBER_RULES

        self.execute_mock.side_effect = self.make_execute_router(
            json.dumps(mock_func_apps),  # graph query for function apps
            {
                "resources-task-def456": {
                    MONITORED_SUBSCRIPTIONS_KEY: mock_monitored_subs_1_json,
                    RESOURCE_TAG_FILTERS_KEY: mock_resource_tag_filters,
                    PII_SCRUBBER_RULES_KEY: "",
                },
                "resources-task-ghi789": {
                    MONITORED_SUBSCRIPTIONS_KEY: mock_monitored_subs_2_json,
                    RESOURCE_TAG_FILTERS_KEY: "",
                    PII_SCRUBBER_RULES_KEY: mock_pii_scrubber_rules,
                },
            },
        )

        result = check_existing_lfo(self.config.all_subscriptions, SUB_ID_TO_NAME)

        self.assertEqual(len(result), 2)
        self.assertIn("def456", result)
        self.assertIn("ghi789", result)

        lfo_1 = result["def456"]
        expected_lfo_1_subs = {
            SUB_1_ID: SUB_ID_TO_NAME[SUB_1_ID],
            SUB_2_ID: SUB_ID_TO_NAME[SUB_2_ID],
        }
        self.assertEqual(lfo_1.monitored_subs, expected_lfo_1_subs)
        self.assertEqual(lfo_1.control_plane.resource_group, "lfo-rg-1")
        self.assertEqual(lfo_1.tag_filter, RESOURCE_TAG_FILTERS)
        self.assertEqual(lfo_1.pii_rules, "")

        lfo_2 = result["ghi789"]
        expected_lfo_2_subs = {
            SUB_3_ID: SUB_ID_TO_NAME[SUB_3_ID],
            SUB_4_ID: SUB_ID_TO_NAME[SUB_4_ID],
        }
        self.assertEqual(lfo_2.monitored_subs, expected_lfo_2_subs)
        self.assertEqual(lfo_2.control_plane.resource_group, "lfo-rg-2")
        self.assertEqual(lfo_2.tag_filter, "")
        self.assertEqual(lfo_2.pii_rules, PII_SCRUBBER_RULES)
