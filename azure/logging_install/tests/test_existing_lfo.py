# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
from unittest import TestCase
from unittest.mock import patch as mock_patch

from azure_logging_install.configuration import Configuration
from azure_logging_install.constants import (
    MONITORED_SUBSCRIPTIONS_KEY,
    PII_SCRUBBER_RULES_KEY,
    RESOURCE_TAG_FILTERS_KEY,
    RESOURCES_TASK_PREFIX,
    SCALING_TASK_PREFIX,
)
from azure_logging_install.existing_lfo import (
    check_existing_lfo,
    find_existing_lfo_control_planes,
    query_function_app_env_vars,
    update_existing_lfo,
)

from logging_install.tests.test_data import (
    CONTROL_PLANE_ID,
    CONTROL_PLANE_REGION,
    CONTROL_PLANE_RESOURCE_GROUP,
    DIAGNOSTIC_SETTINGS_TASK_NAME,
    PII_SCRUBBER_RULES,
    RESOURCE_TAG_FILTERS,
    RESOURCE_TASK_NAME,
    SCALING_TASK_NAME,
    SUB_1_ID,
    SUB_2_ID,
    SUB_3_ID,
    get_test_config,
    make_control_plane,
)


class TestFindExistingLfoControlPlanes(TestCase):
    def setUp(self) -> None:
        self.execute_mock = self.patch("azure_logging_install.existing_lfo.execute")

    def patch(self, path: str, **kwargs):
        """Helper method to patch and auto-cleanup"""
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_empty_subscriptions_set_returns_empty_without_querying(self):
        """Test that an empty (but non-None) subscriptions set short-circuits without any Azure calls"""
        result = find_existing_lfo_control_planes(subscriptions=set())

        self.assertEqual(result, {})
        self.execute_mock.assert_not_called()

    def test_no_control_planes_found(self):
        """Test when no matching resources exist"""
        self.execute_mock.side_effect = ["installed", json.dumps({"data": []})]

        result = find_existing_lfo_control_planes()

        self.assertEqual(result, {})

    def test_finds_control_planes_and_parses_id_from_name(self):
        """Test control planes are constructed from graph query results, with ID parsed from resource name suffix"""
        mock_response = {
            "data": [
                {
                    "name": RESOURCE_TASK_NAME,
                    "resourceGroup": CONTROL_PLANE_RESOURCE_GROUP,
                    "subscriptionId": SUB_1_ID,
                    "location": CONTROL_PLANE_REGION,
                }
            ]
        }
        self.execute_mock.side_effect = ["installed", json.dumps(mock_response)]

        with mock_patch(
            "azure_logging_install.configuration.execute",
            return_value=json.dumps([{"value": "key", "permissions": "FULL"}]),
        ):
            result = find_existing_lfo_control_planes()

        self.assertEqual(len(result), 1)
        self.assertIn(CONTROL_PLANE_ID, result)
        control_plane = result[CONTROL_PLANE_ID]
        self.assertEqual(control_plane.subscription_id, SUB_1_ID)
        self.assertEqual(control_plane.resource_group, CONTROL_PLANE_RESOURCE_GROUP)
        self.assertEqual(control_plane.region, CONTROL_PLANE_REGION)

    def test_installs_resource_graph_extension_if_missing(self):
        """Test resource-graph extension is added when 'extension show' fails"""
        self.execute_mock.side_effect = ["", None, json.dumps({"data": []})]

        find_existing_lfo_control_planes()

        # First call: extension show (can_fail); second: extension add; third: graph query
        self.assertEqual(self.execute_mock.call_count, 3)
        add_call_cmd = str(self.execute_mock.call_args_list[1][0][0])
        self.assertIn("extension", add_call_cmd)
        self.assertIn("add", add_call_cmd)

    def test_subscriptions_filter_included_in_query(self):
        """Test that a subscriptions filter clause is added to the graph query"""
        self.execute_mock.side_effect = ["installed", json.dumps({"data": []})]

        find_existing_lfo_control_planes(subscriptions={SUB_1_ID})

        query_call_cmd = str(self.execute_mock.call_args_list[1][0][0])
        self.assertIn(SUB_1_ID, query_call_cmd)

    def test_invalid_json_raises(self):
        """Test invalid JSON response from graph query raises"""
        self.execute_mock.side_effect = ["installed", "not json"]

        with self.assertRaises(json.JSONDecodeError):
            find_existing_lfo_control_planes()


class TestQueryFunctionAppEnvVars(TestCase):
    def setUp(self) -> None:
        self.execute_mock = self.patch("azure_logging_install.existing_lfo.execute")

    def patch(self, path: str, **kwargs):
        """Helper method to patch and auto-cleanup"""
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_returns_dict_of_env_vars(self):
        """Test env vars list from az cli is converted into a name->value dict"""
        self.execute_mock.return_value = json.dumps(
            [{"name": "FOO", "value": "bar"}, {"name": "BAZ", "value": "qux"}]
        )
        control_plane = make_control_plane()

        result = query_function_app_env_vars(control_plane, RESOURCE_TASK_NAME)

        self.assertEqual(result, {"FOO": "bar", "BAZ": "qux"})

    def test_invalid_json_raises(self):
        """Test invalid JSON response raises"""
        self.execute_mock.return_value = "not json"
        control_plane = make_control_plane()

        with self.assertRaises(json.JSONDecodeError):
            query_function_app_env_vars(control_plane, RESOURCE_TASK_NAME)


class TestCheckExistingLfo(TestCase):
    def setUp(self) -> None:
        """Set up test fixtures"""
        self.execute_mock = self.patch("azure_logging_install.existing_lfo.execute")

        # Create test configuration
        self.config = get_test_config()

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
            cmd = str(az_cmd)
            if "extension show" in cmd:
                return "installed"
            if "graph query" in cmd:
                return func_apps_json
            if "config appsettings list" in cmd:
                func_app_name = cmd.split("--name")[1].split()[0]

                # Return env vars for this function app as a JSON list, like the az cli
                env_vars = func_apps_settings.get(func_app_name, {})
                return json.dumps([{"name": key, "value": value} for key, value in env_vars.items()])
            raise AssertionError(f"Unexpected az cmd: {cmd}")

        return _router

    def test_check_existing_lfo_no_installations(self):
        """Test when no LFO installations exist"""
        self.execute_mock.side_effect = self.make_execute_router(
            json.dumps({"data": []}),  # graph query returns empty data
        )

        result = check_existing_lfo(self.config.all_subscriptions)

        self.assertEqual(result, {})

    def test_check_existing_lfo_single_installation(self):
        """Test with a single existing LFO installation"""
        mock_func_apps = {
            "data": [
                {
                    "resourceGroup": CONTROL_PLANE_RESOURCE_GROUP,
                    "name": RESOURCE_TASK_NAME,
                    "location": CONTROL_PLANE_REGION,
                    "subscriptionId": SUB_1_ID,
                },
                {
                    "resourceGroup": CONTROL_PLANE_RESOURCE_GROUP,
                    "name": SCALING_TASK_NAME,
                    "location": CONTROL_PLANE_REGION,
                    "subscriptionId": SUB_1_ID,
                },
            ]
        }
        mock_monitored_subs_json = json.dumps([SUB_1_ID, SUB_2_ID, SUB_3_ID])

        self.execute_mock.side_effect = self.make_execute_router(
            json.dumps(mock_func_apps),  # graph query for function apps
            {
                RESOURCE_TASK_NAME: {
                    MONITORED_SUBSCRIPTIONS_KEY: mock_monitored_subs_json,
                    RESOURCE_TAG_FILTERS_KEY: RESOURCE_TAG_FILTERS,
                },
                SCALING_TASK_NAME: {
                    PII_SCRUBBER_RULES_KEY: PII_SCRUBBER_RULES,
                },
            },
        )

        with mock_patch(
            "azure_logging_install.configuration.execute",
            return_value=json.dumps([{"value": "key", "permissions": "FULL"}]),
        ):
            result = check_existing_lfo(self.config.all_subscriptions)

        self.assertEqual(len(result), 1)
        self.assertIn(CONTROL_PLANE_ID, result)

        existing_config = result[CONTROL_PLANE_ID]
        self.assertIsInstance(existing_config, Configuration)
        self.assertEqual(existing_config.control_plane.resource_group, CONTROL_PLANE_RESOURCE_GROUP)
        self.assertEqual(existing_config.control_plane.subscription_id, SUB_1_ID)
        self.assertEqual(existing_config.monitored_subscriptions, [SUB_1_ID, SUB_2_ID, SUB_3_ID])
        self.assertEqual(existing_config.resource_tag_filters, RESOURCE_TAG_FILTERS)
        self.assertEqual(existing_config.pii_scrubber_rules, PII_SCRUBBER_RULES)

    def test_check_existing_lfo_multiple_installations(self):
        """Test with multiple existing LFO installations - returns stubs without querying settings"""
        control_plane_1_id = "def456"
        control_plane_2_id = "ghi789"

        mock_func_apps = {
            "data": [
                {
                    "resourceGroup": CONTROL_PLANE_RESOURCE_GROUP,
                    "name": f"{RESOURCES_TASK_PREFIX}{control_plane_1_id}",
                    "location": CONTROL_PLANE_REGION,
                    "subscriptionId": SUB_1_ID,
                },
                {
                    "resourceGroup": CONTROL_PLANE_RESOURCE_GROUP,
                    "name": f"{SCALING_TASK_PREFIX}{control_plane_1_id}",
                    "location": CONTROL_PLANE_REGION,
                    "subscriptionId": SUB_1_ID,
                },
                {
                    "resourceGroup": "lfo-rg-2",
                    "name": f"{RESOURCES_TASK_PREFIX}{control_plane_2_id}",
                    "location": CONTROL_PLANE_REGION,
                    "subscriptionId": SUB_2_ID,
                },
                {
                    "resourceGroup": "lfo-rg-2",
                    "name": f"{SCALING_TASK_PREFIX}{control_plane_2_id}",
                    "location": CONTROL_PLANE_REGION,
                    "subscriptionId": SUB_2_ID,
                },
            ],
        }

        self.execute_mock.side_effect = self.make_execute_router(json.dumps(mock_func_apps))

        with mock_patch(
            "azure_logging_install.configuration.execute",
            return_value=json.dumps([{"value": "key", "permissions": "FULL"}]),
        ):
            result = check_existing_lfo(self.config.all_subscriptions)

        self.assertEqual(len(result), 2)
        self.assertIn(control_plane_1_id, result)
        self.assertIn(control_plane_2_id, result)

        config_1 = result[control_plane_1_id]
        self.assertIsInstance(config_1, Configuration)
        self.assertEqual(config_1.control_plane.resource_group, CONTROL_PLANE_RESOURCE_GROUP)
        # Expect the rest to be empty since we shortcut on multiple LFOs
        self.assertEqual(config_1.monitored_subscriptions, [])
        self.assertEqual(config_1.resource_tag_filters, "")
        self.assertEqual(config_1.pii_scrubber_rules, "")
        self.assertEqual(config_1.datadog_api_key, "")

        config_2 = result[control_plane_2_id]
        self.assertEqual(config_2.control_plane.resource_group, "lfo-rg-2")
        self.assertEqual(config_2.monitored_subscriptions, [])
        self.assertEqual(config_2.resource_tag_filters, "")
        self.assertEqual(config_2.pii_scrubber_rules, "")

    def test_check_existing_lfo_no_monitored_subs_returns_empty(self):
        """Test that a missing/empty MONITORED_SUBSCRIPTIONS env var results in an empty dict"""
        mock_func_apps = {
            "data": [
                {
                    "resourceGroup": CONTROL_PLANE_RESOURCE_GROUP,
                    "name": RESOURCE_TASK_NAME,
                    "location": CONTROL_PLANE_REGION,
                    "subscriptionId": SUB_1_ID,
                },
                {
                    "resourceGroup": CONTROL_PLANE_RESOURCE_GROUP,
                    "name": SCALING_TASK_NAME,
                    "location": CONTROL_PLANE_REGION,
                    "subscriptionId": SUB_1_ID,
                },
            ]
        }

        self.execute_mock.side_effect = self.make_execute_router(json.dumps(mock_func_apps))

        with mock_patch(
            "azure_logging_install.configuration.execute",
            return_value=json.dumps([{"value": "key", "permissions": "FULL"}]),
        ):
            result = check_existing_lfo(self.config.all_subscriptions)

        self.assertEqual(result, {})


class TestUpdateExistingLfo(TestCase):
    def setUp(self) -> None:
        self.mock_set_env_vars = self.patch("azure_logging_install.existing_lfo.set_function_app_env_vars")
        self.mock_set_monitored_subs = self.patch("azure_logging_install.existing_lfo.set_monitored_subscriptions")
        self.mock_set_tag_filters = self.patch("azure_logging_install.existing_lfo.set_resource_tag_filters")
        self.mock_set_pii_rules = self.patch("azure_logging_install.existing_lfo.set_pii_scrubber_rules")
        self.mock_grant_subs_perms = self.patch("azure_logging_install.existing_lfo.grant_subscriptions_permissions")
        self.mock_revoke_subs_perms = self.patch("azure_logging_install.existing_lfo.revoke_subscriptions_permissions")

    def patch(self, path: str, **kwargs):
        """Helper method to patch and auto-cleanup"""
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_update_existing_lfo_monitored_subs_only(self):
        """Test successful update of existing LFO installation - new subscriptions only"""
        new_config = get_test_config()
        new_config.monitored_subscriptions = [SUB_1_ID, SUB_2_ID, SUB_3_ID]

        existing_config = get_test_config()
        existing_config.monitored_subscriptions = [SUB_1_ID, SUB_2_ID]

        update_existing_lfo(new_config, existing_config)

        # Only monitored set changed: partial update (set_monitored_subscriptions), not full env vars
        self.mock_set_env_vars.assert_not_called()
        self.mock_set_monitored_subs.assert_called_once_with(existing_config)
        self.mock_set_tag_filters.assert_not_called()
        self.mock_set_pii_rules.assert_not_called()
        self.mock_revoke_subs_perms.assert_not_called()
        self.mock_grant_subs_perms.assert_called_once_with(existing_config, {SUB_3_ID})

    def test_update_existing_lfo_remove_scopes_only(self):
        """Test update when only subscriptions are removed (no tag/pii change); revoke and partial env update."""
        new_config = get_test_config()
        new_config.monitored_subscriptions = [SUB_1_ID]

        existing_config = get_test_config()
        existing_config.monitored_subscriptions = [SUB_1_ID, SUB_2_ID]

        update_existing_lfo(new_config, existing_config)

        self.mock_set_env_vars.assert_not_called()
        self.mock_set_monitored_subs.assert_called_once_with(existing_config)
        self.mock_set_tag_filters.assert_not_called()
        self.mock_set_pii_rules.assert_not_called()
        self.mock_revoke_subs_perms.assert_called_once()
        call_args = self.mock_revoke_subs_perms.call_args[0]
        self.assertEqual(call_args[0], existing_config)
        self.assertEqual(set(call_args[1]), {SUB_2_ID})
        self.mock_grant_subs_perms.assert_not_called()

    def test_update_existing_lfo_add_and_remove_monitored_only(self):
        """Test update when only monitored set changes (add SUB_3, remove SUB_2); partial update, grant and revoke."""
        new_config = get_test_config()
        new_config.monitored_subscriptions = [SUB_1_ID, SUB_3_ID]

        existing_config = get_test_config()
        existing_config.monitored_subscriptions = [SUB_1_ID, SUB_2_ID]

        update_existing_lfo(new_config, existing_config)

        self.mock_set_env_vars.assert_not_called()
        self.mock_set_monitored_subs.assert_called_once_with(existing_config)
        self.mock_set_tag_filters.assert_not_called()
        self.mock_set_pii_rules.assert_not_called()
        self.mock_grant_subs_perms.assert_called_once_with(existing_config, {SUB_3_ID})
        self.mock_revoke_subs_perms.assert_called_once_with(existing_config, {SUB_2_ID})

    def test_update_existing_lfo_tag_filter_only(self):
        """Test update when only tag filter changes; partial update via set_resource_tag_filters."""
        new_config = get_test_config()

        existing_config = get_test_config()
        existing_config.resource_tag_filters = "env:staging,team:legacy"

        update_existing_lfo(new_config, existing_config)

        self.mock_set_env_vars.assert_not_called()
        self.mock_set_monitored_subs.assert_not_called()
        self.mock_set_tag_filters.assert_called_once_with(existing_config)
        self.mock_set_pii_rules.assert_not_called()
        self.mock_grant_subs_perms.assert_not_called()
        self.mock_revoke_subs_perms.assert_not_called()

    def test_update_existing_lfo_pii_rules_only(self):
        """Test update when only PII rules change; partial update via set_pii_scrubber_rules."""
        new_config = get_test_config()

        existing_config = get_test_config()
        existing_config.pii_scrubber_rules = "old-rule:\n  pattern: 'old'\n  replacement: 'REDACTED'"

        update_existing_lfo(new_config, existing_config)

        self.mock_set_env_vars.assert_not_called()
        self.mock_set_monitored_subs.assert_not_called()
        self.mock_set_tag_filters.assert_not_called()
        self.mock_set_pii_rules.assert_called_once_with(existing_config)
        self.mock_grant_subs_perms.assert_not_called()
        self.mock_revoke_subs_perms.assert_not_called()

    def test_update_existing_lfo_tag_filter_pii_settings(self):
        """Test update when no new subscriptions are added but tag filters and PII rules change"""
        new_config = get_test_config()

        existing_config = get_test_config()
        existing_config.resource_tag_filters = "env:staging,team:legacy"
        existing_config.pii_scrubber_rules = "old-rule:\n  pattern: 'old pattern'\n  replacement: 'OLD'"

        update_existing_lfo(new_config, existing_config)

        # Tag + pii changed (2 changes): full env var update for all task function apps
        self.assertEqual(self.mock_set_env_vars.call_count, 3)
        for task_name in existing_config.control_plane.task_names:
            self.mock_set_env_vars.assert_any_call(existing_config, task_name)
        self.mock_set_monitored_subs.assert_not_called()
        self.mock_set_tag_filters.assert_not_called()
        self.mock_set_pii_rules.assert_not_called()
        self.mock_revoke_subs_perms.assert_not_called()
        self.mock_grant_subs_perms.assert_not_called()

    def test_update_existing_lfo_tag_and_monitored(self):
        """Test update when tag filter and monitored subscriptions both change; full env update."""
        new_config = get_test_config()
        new_config.monitored_subscriptions = [SUB_1_ID, SUB_2_ID, SUB_3_ID]

        existing_config = get_test_config()
        existing_config.monitored_subscriptions = [SUB_1_ID, SUB_2_ID]
        existing_config.resource_tag_filters = "env:staging,team:legacy"

        update_existing_lfo(new_config, existing_config)

        self.assertEqual(self.mock_set_env_vars.call_count, 3)
        self.mock_set_monitored_subs.assert_not_called()
        self.mock_set_tag_filters.assert_not_called()
        self.mock_set_pii_rules.assert_not_called()
        self.mock_grant_subs_perms.assert_called_once_with(existing_config, {SUB_3_ID})
        self.mock_revoke_subs_perms.assert_not_called()

    def test_update_existing_lfo_pii_and_monitored(self):
        """Test update when PII rules and monitored subscriptions both change; full env update."""
        new_config = get_test_config()
        new_config.monitored_subscriptions = [SUB_1_ID]

        existing_config = get_test_config()
        existing_config.monitored_subscriptions = [SUB_1_ID, SUB_2_ID]
        existing_config.pii_scrubber_rules = "old-rule:\n  pattern: 'old'\n  replacement: 'REDACTED'"

        update_existing_lfo(new_config, existing_config)

        self.assertEqual(self.mock_set_env_vars.call_count, 3)
        self.mock_set_monitored_subs.assert_not_called()
        self.mock_set_tag_filters.assert_not_called()
        self.mock_set_pii_rules.assert_not_called()
        self.mock_grant_subs_perms.assert_not_called()
        self.mock_revoke_subs_perms.assert_called_once()
        self.assertEqual(set(self.mock_revoke_subs_perms.call_args[0][1]), {SUB_2_ID})

    def test_update_existing_lfo_all_three_changed(self):
        """Test update when tag, PII, and monitored subscriptions all change; full env update."""
        new_config = get_test_config()
        new_config.monitored_subscriptions = [SUB_1_ID, SUB_2_ID, SUB_3_ID]
        new_config.resource_tag_filters = "env:new,team:new"
        new_config.pii_scrubber_rules = "new-rule:\n  pattern: 'new'\n  replacement: 'MASKED'"

        existing_config = get_test_config()
        existing_config.monitored_subscriptions = [SUB_1_ID, SUB_2_ID]

        update_existing_lfo(new_config, existing_config)

        self.assertEqual(self.mock_set_env_vars.call_count, 3)
        self.mock_set_monitored_subs.assert_not_called()
        self.mock_set_tag_filters.assert_not_called()
        self.mock_set_pii_rules.assert_not_called()
        self.mock_grant_subs_perms.assert_called_once_with(existing_config, {SUB_3_ID})
        self.mock_revoke_subs_perms.assert_not_called()

    def test_update_existing_lfo_noop(self):
        """Test update when no changes are needed"""
        new_config = get_test_config()
        existing_config = get_test_config()

        update_existing_lfo(new_config, existing_config)

        self.mock_set_env_vars.assert_not_called()
        self.mock_set_monitored_subs.assert_not_called()
        self.mock_set_tag_filters.assert_not_called()
        self.mock_set_pii_rules.assert_not_called()
        self.mock_grant_subs_perms.assert_not_called()
        self.mock_revoke_subs_perms.assert_not_called()
