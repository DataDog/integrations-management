# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Tests for quickstart_shared: build_log_forwarder_payload and report_existing_log_forwarders (Section 7: optional monitoredSubscriptions)."""

import os
from unittest.mock import MagicMock
from unittest.mock import patch as mock_patch

from azure_integration_quickstart.quickstart_shared import (
    build_log_forwarder_payload,
    report_existing_log_forwarders,
    upsert_log_forwarder,
)
from azure_integration_quickstart.script_status import Status
from azure_logging_install.existing_lfo import LfoControlPlane, LfoMetadata

from integration_quickstart.tests.dd_test_case import DDTestCase


def _make_metadata(monitored_subs=None):
    if monitored_subs is None:
        monitored_subs = {"sub-1": "Sub One", "sub-2": "Sub Two"}
    return LfoMetadata(
        control_plane=LfoControlPlane(
            sub_id="cp-sub",
            sub_name="Control Plane Sub",
            resource_group="lfo-rg",
            region="eastus",
        ),
        monitored_subs=monitored_subs,
        tag_filter="env:prod",
        pii_rules="rule: redact",
    )


class TestBuildLogForwarderPayload(DDTestCase):
    """Optional monitoredSubscriptions in payload only when include_monitored_scopes is True."""

    def test_include_monitored_scopes_true_includes_monitored_subscriptions(self):
        metadata = _make_metadata()
        payload = build_log_forwarder_payload(metadata, include_monitored_scopes=True)
        self.assertIn("monitoredSubscriptions", payload)
        self.assertEqual(
            payload["monitoredSubscriptions"],
            [{"id": "sub-1", "name": "Sub One"}, {"id": "sub-2", "name": "Sub Two"}],
        )
        self.assertEqual(payload["resourceGroupName"], "lfo-rg")
        self.assertEqual(payload["controlPlaneSubscriptionId"], "cp-sub")

    def test_include_monitored_scopes_false_omits_monitored_subscriptions(self):
        metadata = _make_metadata()
        payload = build_log_forwarder_payload(metadata, include_monitored_scopes=False)
        self.assertNotIn("monitoredSubscriptions", payload)
        self.assertEqual(payload["resourceGroupName"], "lfo-rg")


class TestUpsertLogForwarderWaitForRgDelete(DDTestCase):
    """wait_for_rg_delete step is reported only when on_rg_waiting callbacks fire."""

    def setUp(self):
        self.install_mock = self.patch("azure_integration_quickstart.quickstart_shared.install_log_forwarder")
        env_patcher = mock_patch.dict(os.environ, {"DD_API_KEY": "key", "DD_SITE": "datadoghq.com"})
        self.addCleanup(env_patcher.stop)
        env_patcher.start()
        self.config = {
            "controlPlaneRegion": "eastus",
            "controlPlaneSubscriptionId": "cp-sub",
            "resourceGroupName": "lfo-rg",
        }
        self.status = MagicMock()

    def _capture_callbacks(self):
        """Return the on_rg_waiting_start and on_rg_waiting_end kwargs captured by install_log_forwarder."""
        _, kwargs = self.install_mock.call_args
        return kwargs["on_rg_waiting_start"], kwargs["on_rg_waiting_end"]

    def test_wait_for_rg_delete_reported_when_callbacks_fire(self):
        upsert_log_forwarder(self.config, set(), self.status)
        on_start, on_end = self._capture_callbacks()

        on_start()
        self.status.report.assert_called_once_with(
            "wait_for_rg_delete",
            Status.IN_PROGRESS,
            "Waiting for existing resource group deletion to complete before recreating it.",
        )

        on_end()
        self.status.report.assert_called_with(
            "wait_for_rg_delete", Status.FINISHED, "Resource group deletion complete."
        )

    def test_on_end_does_nothing_if_on_start_never_fired(self):
        upsert_log_forwarder(self.config, set(), self.status)
        _, on_end = self._capture_callbacks()

        on_end()
        self.status.report.assert_not_called()


class TestReportExistingLogForwarders(DDTestCase):
    """report_existing_log_forwarders populates step_metadata and returns existing_lfo or None."""

    def test_one_lfo_populates_step_metadata_and_returns_metadata(self):
        """With one existing LFO, step_metadata gets one payload and we return that LfoMetadata."""
        metadata = _make_metadata()
        step_metadata = {}
        with mock_patch(
            "azure_integration_quickstart.quickstart_shared.check_existing_lfo",
            return_value={"lfo-id": metadata},
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
