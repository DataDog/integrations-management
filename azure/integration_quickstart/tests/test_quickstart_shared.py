# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

"""Tests for quickstart_shared: build_log_forwarder_payload and report_existing_log_forwarders (Section 7: optional monitoredSubscriptions)."""

from unittest.mock import patch as mock_patch

from azure_logging_install.existing_lfo import LfoControlPlane, LfoMetadata

from azure_integration_quickstart.quickstart_shared import (
    build_log_forwarder_payload,
    report_existing_log_forwarders,
)

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


class TestReportExistingLogForwarders(DDTestCase):
    """report_existing_log_forwarders populates step_metadata and returns (exactly_one, existing_lfo)."""

    def test_one_lfo_populates_step_metadata_and_returns_exactly_one_and_metadata(self):
        """With one existing LFO, step_metadata gets one payload and we return (True, that LfoMetadata)."""
        metadata = _make_metadata()
        step_metadata = {}
        with mock_patch(
            "azure_integration_quickstart.quickstart_shared.check_existing_lfo",
            return_value={"lfo-id": metadata},
        ):
            exactly_one, existing_lfo = report_existing_log_forwarders(
                [], step_metadata, include_monitored_scopes=True
            )
        self.assertTrue(exactly_one)
        self.assertIs(existing_lfo, metadata)
        self.assertEqual(len(step_metadata["log_forwarders"]), 1)
        self.assertEqual(step_metadata["log_forwarders"][0]["controlPlaneSubscriptionId"], "cp-sub")

    def test_no_existing_lfos_returns_false_none_and_empty_list_so_quickstart_creates_new(self):
        """When there are zero LFOs in the tenant, return (False, None) and write []."""
        step_metadata = {}
        with mock_patch(
            "azure_integration_quickstart.quickstart_shared.check_existing_lfo",
            return_value={},
        ):
            exactly_one, existing_lfo = report_existing_log_forwarders(
                [], step_metadata, include_monitored_scopes=True
            )
        self.assertFalse(exactly_one)
        self.assertIsNone(existing_lfo)
        self.assertEqual(step_metadata["log_forwarders"], [])
