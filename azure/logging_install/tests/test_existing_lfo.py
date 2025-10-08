# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

# stdlib
import json
from unittest import TestCase
from unittest.mock import patch as mock_patch

# project
from azure_logging_install.existing_lfo import (
    check_existing_lfo,
    update_existing_lfo,
    LfoMetadata,
    MONITORED_SUBSCRIPTIONS_KEY,
    RESOURCE_TAG_FILTERS_KEY,
    PII_SCRUBBER_RULES_KEY,
    LfoControlPlane,
    UNKNOWN_SUB_NAME_MESSAGE,
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
    RESOURCE_TASK_NAME,
    PII_SCRUBBER_RULES,
    CONTROL_PLANE_ID,
    SCALING_TASK_NAME,
    DIAGNOSTIC_SETTINGS_TASK_NAME,
    CONTROL_PLANE_SUBSCRIPTION_NAME,
    get_test_config,
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
                    "name": RESOURCE_TASK_NAME,
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
                RESOURCE_TASK_NAME: {
                    MONITORED_SUBSCRIPTIONS_KEY: mock_monitored_subs_json,
                    RESOURCE_TAG_FILTERS_KEY: RESOURCE_TAG_FILTERS,
                    PII_SCRUBBER_RULES_KEY: PII_SCRUBBER_RULES,
                }
            },
        )

        result = check_existing_lfo(self.config.all_subscriptions, SUB_ID_TO_NAME)

        self.assertEqual(len(result), 1)
        self.assertIn(CONTROL_PLANE_ID, result)

        lfo_metadata = result[CONTROL_PLANE_ID]
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

    def test_check_existing_lfo_insufficient_sub_permissions(self):
        """Test with an existing LFO installation where the user doesn't have permissions to read a monitored subscription"""
        unknown_sub_id = "unknown-sub-id"
        mock_func_apps = {
            "data": [
                {
                    "resourceGroup": "lfo-rg",
                    "name": RESOURCE_TASK_NAME,
                    "location": "eastus",
                    "subscriptionId": SUB_1_ID,
                }
            ]
        }
        mock_monitored_subs_json = json.dumps(
            {
                SUB_1_ID: SUB_ID_TO_NAME[SUB_1_ID],
                SUB_2_ID: SUB_ID_TO_NAME[SUB_2_ID],
                unknown_sub_id: "User doesn't have access to read the subscription name",
            }
        )

        self.execute_mock.side_effect = self.make_execute_router(
            json.dumps(mock_func_apps),
            {
                RESOURCE_TASK_NAME: {
                    MONITORED_SUBSCRIPTIONS_KEY: mock_monitored_subs_json,
                }
            },
        )

        result = check_existing_lfo(self.config.all_subscriptions, SUB_ID_TO_NAME)

        self.assertEqual(len(result), 1)
        self.assertIn(CONTROL_PLANE_ID, result)

        lfo_metadata = result[CONTROL_PLANE_ID]
        self.assertIsInstance(lfo_metadata, LfoMetadata)
        self.assertEqual(
            lfo_metadata.monitored_subs,
            {
                SUB_1_ID: SUB_ID_TO_NAME[SUB_1_ID],
                SUB_2_ID: SUB_ID_TO_NAME[SUB_2_ID],
                unknown_sub_id: UNKNOWN_SUB_NAME_MESSAGE,
            },
        )

    def test_update_existing_lfo_monitored_subs_only(self):
        """Test successful update of existing LFO installation - new subscriptions only"""

        # test_config is new config with only a new subscription (sub 3)
        test_config = get_test_config()
        test_config.monitored_subscriptions = [SUB_1_ID, SUB_2_ID, SUB_3_ID]

        # Existing LFO has some overlapping subscriptions, but no sub 3. Filters & PII rules remain the same
        existing_lfos = {
            CONTROL_PLANE_ID: LfoMetadata(
                control_plane=LfoControlPlane(
                    CONTROL_PLANE_SUBSCRIPTION_ID,
                    CONTROL_PLANE_SUBSCRIPTION_NAME,
                    CONTROL_PLANE_RESOURCE_GROUP,
                    CONTROL_PLANE_REGION,
                ),
                monitored_subs={
                    SUB_1_ID: SUB_ID_TO_NAME[SUB_1_ID],
                    SUB_2_ID: SUB_ID_TO_NAME[SUB_2_ID],
                },
                tag_filter=RESOURCE_TAG_FILTERS,
                pii_rules=PII_SCRUBBER_RULES,
            )
        }

        with (
            mock_patch(
                "azure_logging_install.existing_lfo.set_function_app_env_vars"
            ) as mock_set_env_vars,
            mock_patch(
                "azure_logging_install.existing_lfo.grant_subscriptions_permissions"
            ) as mock_grant_subs_perms,
        ):
            existing_lfo = next(iter(existing_lfos.values()))
            update_existing_lfo(test_config, existing_lfo)

            # Verify function app environment variables are not updated since they remain the same
            self.assertEqual(mock_set_env_vars.call_count, 0)

            # Verify permissions are granted only for new subscription
            mock_grant_subs_perms.assert_called_once_with(test_config, {SUB_3_ID})

    def test_update_existing_lfo_tag_filter_pii_settings(self):
        """Test update when no new subscriptions are added but tag filters and PII rules change"""

        # test_config is new config with new tag filters and PII rules, but same monitored subs
        test_config = get_test_config()

        # Existing LFO has same monitored subs, but old tag filters and PII rules
        existing_lfos = {
            CONTROL_PLANE_ID: LfoMetadata(
                control_plane=LfoControlPlane(
                    test_config.control_plane_sub_id,
                    SUB_ID_TO_NAME[test_config.control_plane_sub_id],
                    test_config.control_plane_rg,
                    test_config.control_plane_region,
                ),
                monitored_subs={
                    sub_id: SUB_ID_TO_NAME[sub_id]
                    for sub_id in test_config.monitored_subscriptions
                },
                tag_filter="env:staging,team:legacy",
                pii_rules="old-rule:\n  pattern: 'old pattern'\n  replacement: 'OLD'",
            )
        }

        with (
            mock_patch(
                "azure_logging_install.existing_lfo.set_function_app_env_vars"
            ) as mock_set_env_vars,
            mock_patch(
                "azure_logging_install.existing_lfo.grant_subscriptions_permissions"
            ) as mock_grant_subs_perms,
        ):
            existing_lfo = next(iter(existing_lfos.values()))
            update_existing_lfo(test_config, existing_lfo)

            # Verify call for env var updates with new tag filters and PII rules
            self.assertEqual(mock_set_env_vars.call_count, 3)
            mock_set_env_vars.assert_any_call(test_config, RESOURCE_TASK_NAME)
            mock_set_env_vars.assert_any_call(test_config, SCALING_TASK_NAME)
            mock_set_env_vars.assert_any_call(
                test_config, DIAGNOSTIC_SETTINGS_TASK_NAME
            )

            # Verify the config passed to set_function_app_env_vars has the updated values
            call_args = mock_set_env_vars.call_args[0]
            updated_config = call_args[0]
            self.assertEqual(updated_config.resource_tag_filters, RESOURCE_TAG_FILTERS)
            self.assertEqual(updated_config.pii_scrubber_rules, PII_SCRUBBER_RULES)

            # Verify no new subscription permissions granted
            mock_grant_subs_perms.assert_not_called()

    def test_update_existing_lfo_noop(self):
        """Test update when no changes are needed"""

        # test_config is same as existing LFO
        test_config = get_test_config()
        existing_lfos = {
            CONTROL_PLANE_ID: LfoMetadata(
                control_plane=LfoControlPlane(
                    test_config.control_plane_sub_id,
                    SUB_ID_TO_NAME[test_config.control_plane_sub_id],
                    test_config.control_plane_rg,
                    test_config.control_plane_region,
                ),
                monitored_subs={
                    sub_id: SUB_ID_TO_NAME[sub_id]
                    for sub_id in test_config.monitored_subscriptions
                },
                tag_filter=RESOURCE_TAG_FILTERS,
                pii_rules=PII_SCRUBBER_RULES,
            )
        }

        with (
            mock_patch(
                "azure_logging_install.existing_lfo.set_function_app_env_vars"
            ) as mock_set_env_vars,
            mock_patch(
                "azure_logging_install.existing_lfo.grant_subscriptions_permissions"
            ) as mock_grant_subs_perms,
        ):
            existing_lfo = next(iter(existing_lfos.values()))
            update_existing_lfo(test_config, existing_lfo)

            # Verify no function app environment variables are updated
            mock_set_env_vars.assert_not_called()

            # Verify no new subscription permissions granted
            mock_grant_subs_perms.assert_not_called()
