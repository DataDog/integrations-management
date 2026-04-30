# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Tests for quickstart_shared: build_log_forwarder_payload and report_existing_log_forwarders (Section 7: optional monitoredSubscriptions)."""

from unittest.mock import MagicMock
from unittest.mock import patch as mock_patch

from azure_integration_quickstart.quickstart_shared import (
    build_log_forwarder_payload,
    report_existing_log_forwarders,
    wait_for_rg_delete_if_needed,
)
from az_shared.script_status import Status
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
