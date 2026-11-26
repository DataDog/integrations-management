# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Tests for quickstart_shared: build_log_forwarder_payload and report_existing_log_forwarders (Section 7: optional monitoredSubscriptions)."""

import json
import os
from unittest.mock import MagicMock
from unittest.mock import patch as mock_patch

from azure_integration_quickstart.quickstart_shared import (
    build_log_forwarder_payload,
    report_existing_log_forwarders,
    resource_provider_configs_to_selection,
    resource_provider_selection_to_configs,
    upsert_log_forwarder,
    wait_for_rg_delete_if_needed,
)
from az_shared.errors import InputParamValidationError
from az_shared.script_status import Status
from azure_logging_install.existing_lfo import ControlPlane, Configuration
from azure_logging_install.configuration import ControlPlaneType

from integration_quickstart.tests.dd_test_case import DDTestCase


def _make_metadata(monitored_subs=None):
    if monitored_subs is None:
        monitored_subs = "sub-1,sub-2"
    return Configuration(
        control_plane=ControlPlane(
            id="cp-id",
            sub_id="cp-sub",
            resource_group="lfo-rg",
            region="eastus",
            type=ControlPlaneType.ContainerAppJobs,
        ),
        datadog_api_key="",
        monitored_subs=monitored_subs,
        resource_tag_filters="env:prod",
        resource_provider_configs=RESOURCE_PROVIDER_CONFIGS,
        pii_scrubber_rules="rule: redact",
    )


RESOURCE_PROVIDER_SELECTION = {"logsEnabledDefault": True, "resourceProviderExceptions": ["Microsoft.Sql", "Microsoft.Web"]}
RESOURCE_PROVIDER_CONFIGS = (
    '{"logs_enabled_default":true,"providers":['
    '{"logs_enabled":false,"namespace":"Microsoft.Sql"},'
    '{"logs_enabled":false,"namespace":"Microsoft.Web"}]}'
)


class TestBuildLogForwarderPayload(DDTestCase):
    """Optional monitoredSubscriptions in payload only when include_monitored_scopes is True."""

    def test_include_monitored_scopes_true_includes_monitored_subscriptions(self):
        metadata = _make_metadata()
        sub_id_to_name = {"sub-1": "Sub One", "sub-2": "Sub Two"}
        payload = build_log_forwarder_payload(metadata, include_monitored_scopes=True, sub_id_to_name=sub_id_to_name)
        self.assertIn("monitoredSubscriptions", payload)
        self.assertEqual(
            payload["monitoredSubscriptions"],
            [{"id": "sub-1", "name": "Sub One"}, {"id": "sub-2", "name": "Sub Two"}],
        )
        self.assertEqual(payload["resourceGroupName"], "lfo-rg")
        self.assertEqual(payload["controlPlaneSubscriptionId"], "cp-sub")

    def test_include_monitored_scopes_false_omits_monitored_subscriptions(self):
        metadata = _make_metadata()
        sub_id_to_name = {"sub-1": "Sub One", "sub-2": "Sub Two"}
        payload = build_log_forwarder_payload(metadata, include_monitored_scopes=False, sub_id_to_name=sub_id_to_name)
        self.assertNotIn("monitoredSubscriptions", payload)
        self.assertEqual(payload["resourceGroupName"], "lfo-rg")

    def test_reports_resource_provider_selection(self):
        payload = build_log_forwarder_payload(_make_metadata(), include_monitored_scopes=False, sub_id_to_name={})
        self.assertEqual(payload["resourceProviderSelection"], RESOURCE_PROVIDER_SELECTION)


class TestResourceProviderSelectionToConfigs(DDTestCase):
    def test_converts_selection_to_log_forwarder_setting(self):
        self.assertEqual(resource_provider_selection_to_configs(RESOURCE_PROVIDER_SELECTION), RESOURCE_PROVIDER_CONFIGS)

    def test_disabled_by_default_enables_exceptions(self):
        configs = resource_provider_selection_to_configs(
            {"logsEnabledDefault": False, "resourceProviderExceptions": ["Microsoft.Web"]}
        )
        self.assertEqual(
            json.loads(configs),
            {"logs_enabled_default": False, "providers": [{"namespace": "Microsoft.Web", "logs_enabled": True}]},
        )

    def test_same_selection_converts_to_same_setting(self):
        """Exceptions are deduplicated and sorted, so an unchanged selection doesn't update the log forwarder."""
        configs = resource_provider_selection_to_configs(
            {"logsEnabledDefault": True, "resourceProviderExceptions": ["Microsoft.Web", "microsoft.sql", "Microsoft.Sql", " "]}
        )
        self.assertEqual(configs, RESOURCE_PROVIDER_CONFIGS)

    def test_missing_selection_converts_to_empty_setting(self):
        for missing in (None, {}):
            with self.subTest(missing=missing):
                self.assertEqual(resource_provider_selection_to_configs(missing), "")

    def test_invalid_selection_raises_input_param_validation_error(self):
        for invalid in (
            {"logsEnabledDefault": "true"},
            {"resourceProviderExceptions": "Microsoft.Web"},
            {"resourceProviderExceptions": [1]},
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(InputParamValidationError):
                    resource_provider_selection_to_configs(invalid)


class TestResourceProviderConfigsToSelection(DDTestCase):
    def test_converts_log_forwarder_setting_to_selection(self):
        self.assertEqual(resource_provider_configs_to_selection(RESOURCE_PROVIDER_CONFIGS), RESOURCE_PROVIDER_SELECTION)

    def test_round_trips(self):
        selection = {"logsEnabledDefault": False, "resourceProviderExceptions": ["Microsoft.KeyVault", "Microsoft.Web"]}
        self.assertEqual(
            resource_provider_configs_to_selection(resource_provider_selection_to_configs(selection)), selection
        )

    def test_resolves_overrides_like_the_log_forwarder(self):
        """The last override for a resource provider wins, and overrides that match the default aren't exceptions."""
        configs = json.dumps(
            {
                "providers": [
                    {"namespace": "Microsoft.Web", "logs_enabled": False},
                    {"namespace": "microsoft.web", "logs_enabled": True},
                    {"namespace": "Microsoft.Sql", "logs_enabled": True},
                    {"namespace": " Microsoft.KeyVault ", "logs_enabled": False},
                ]
            }
        )
        self.assertEqual(
            resource_provider_configs_to_selection(configs),
            {"logsEnabledDefault": True, "resourceProviderExceptions": ["Microsoft.KeyVault"]},
        )

    def test_empty_or_invalid_setting_enables_all_resource_providers(self):
        all_enabled = {"logsEnabledDefault": True, "resourceProviderExceptions": []}
        for configs in ("", "{}", "not json", "[]", '{"logs_enabled_default": "no", "providers": [{"namespace": 1}]}'):
            with self.subTest(configs=configs):
                self.assertEqual(resource_provider_configs_to_selection(configs), all_enabled)


class TestWaitForRgDeleteIfNeeded(DDTestCase):
    """wait_for_rg_delete step is reported only when an RG is actually found in Deleting state."""

    def setUp(self):
        self.ensure_mock = self.patch(
            "azure_integration_quickstart.quickstart_shared.ensure_control_plane_rg_not_deleting"
        )
        self.status = MagicMock()

    def test_empty_subs_skips_check_and_reports_nothing(self):
        wait_for_rg_delete_if_needed("lfo-rg", set(), self.status)
        self.ensure_mock.assert_not_called()
        self.status.report.assert_not_called()

    def test_in_progress_reported_when_on_start_fires(self):
        def fire_on_start(rg_name, subs, on_rg_waiting_start):
            on_rg_waiting_start()

        self.ensure_mock.side_effect = fire_on_start
        wait_for_rg_delete_if_needed("lfo-rg", {"sub-1"}, self.status)
        self.status.report.assert_any_call(
            "wait_for_rg_delete",
            Status.IN_PROGRESS,
            "Waiting for existing resource group deletion to complete before recreating it.",
        )

    def test_finished_reported_after_wait_when_on_start_fired(self):
        def fire_on_start(rg_name, subs, on_rg_waiting_start):
            on_rg_waiting_start()

        self.ensure_mock.side_effect = fire_on_start
        wait_for_rg_delete_if_needed("lfo-rg", {"sub-1"}, self.status)
        self.status.report.assert_called_with(
            "wait_for_rg_delete", Status.FINISHED, "Resource group deletion complete."
        )

    def test_no_step_reported_when_on_start_never_fires(self):
        self.ensure_mock.return_value = None  # on_start never called
        wait_for_rg_delete_if_needed("lfo-rg", {"sub-1"}, self.status)
        self.status.report.assert_not_called()


class TestReportExistingLogForwarders(DDTestCase):
    """report_existing_log_forwarders populates step_metadata and returns existing_lfo or None."""

    def test_one_lfo_populates_step_metadata_and_returns_metadata(self):
        """With one existing LFO, step_metadata gets one payload and we return that Configuration."""
        metadata = _make_metadata()
        step_metadata = {}
        with mock_patch(
            "azure_integration_quickstart.quickstart_shared.check_existing_lfo",
            return_value=[metadata],
        ):
            existing_lfo = report_existing_log_forwarders([], step_metadata, include_monitored_scopes=True)
        self.assertIs(existing_lfo, metadata)
        self.assertEqual(len(step_metadata["log_forwarders"]), 1)
        self.assertEqual(step_metadata["log_forwarders"][0]["controlPlaneSubscriptionId"], "cp-sub")

    def test_no_existing_lfos_returns_none_and_empty_list_so_quickstart_creates_new(self):
        """When there are zero LFOs in the tenant, return None and write []."""
        step_metadata = {}
        with mock_patch(
            "azure_integration_quickstart.quickstart_shared.check_existing_lfo",
            return_value={},
        ):
            existing_lfo = report_existing_log_forwarders([], step_metadata, include_monitored_scopes=True)
        self.assertIsNone(existing_lfo)
        self.assertEqual(step_metadata["log_forwarders"], [])


class TestUpsertLogForwarder(DDTestCase):
    """upsert_log_forwarder builds a Configuration from the submitted config and subscriptions, then installs it."""

    def setUp(self):
        self.install_mock = self.patch("azure_integration_quickstart.quickstart_shared.install_log_forwarder")
        env_patcher = mock_patch.dict(os.environ, {"DD_API_KEY": "test-api-key", "DD_SITE": "datadoghq.com"})
        env_patcher.start()
        self.addCleanup(env_patcher.stop)

    def test_builds_configuration_from_config_and_subscriptions(self):
        config = {
            "controlPlaneSubscriptionId": "cp-sub",
            "controlPlaneSubscriptionName": "Control Plane Sub",
            "resourceGroupName": "lfo-rg",
            "controlPlaneRegion": "eastus",
            "tagFilters": "env:prod",
            "piiFilters": "rule: redact",
        }
        subscriptions = {"sub-1"}

        upsert_log_forwarder(config, subscriptions)

        self.install_mock.assert_called_once()
        configuration = self.install_mock.call_args[0][0]
        self.assertEqual(configuration.control_plane.sub_id, "cp-sub")
        self.assertEqual(configuration.control_plane.resource_group, "lfo-rg")
        self.assertEqual(configuration.control_plane.region, "eastus")
        self.assertEqual(configuration.monitored_subscriptions, ["sub-1"])
        self.assertEqual(configuration.resource_tag_filters, "env:prod")
        self.assertEqual(configuration.resource_provider_configs, "")
        self.assertEqual(configuration.pii_scrubber_rules, "rule: redact")
        self.assertEqual(configuration.datadog_api_key, "test-api-key")
        self.assertEqual(configuration.datadog_site, "datadoghq.com")

    def test_converts_resource_provider_selection_for_log_forwarder(self):
        config = {
            "controlPlaneSubscriptionId": "cp-sub",
            "resourceGroupName": "lfo-rg",
            "controlPlaneRegion": "eastus",
            "resourceProviderSelection": RESOURCE_PROVIDER_SELECTION,
        }

        upsert_log_forwarder(config, {"sub-1"})

        configuration = self.install_mock.call_args[0][0]
        self.assertEqual(configuration.resource_provider_configs, RESOURCE_PROVIDER_CONFIGS)
