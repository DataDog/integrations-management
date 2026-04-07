# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
from unittest import TestCase
from unittest.mock import patch as mock_patch

from az_shared.errors import ResourceGroupDeletionWaitTimeoutError, ResourceGroupNotFoundError
from azure_logging_install.configuration import Configuration
from azure_logging_install.role_setup import ensure_control_plane_rg_not_deleting

from logging_install.tests.test_data import CONTROL_PLANE_REGION, CONTROL_PLANE_RESOURCE_GROUP


class TestWaitUntilControlPlaneRgReadyForGrant(TestCase):
    def setUp(self) -> None:
        self.execute_mock = self.patch("azure_logging_install.role_setup.execute")
        self.sleep_mock = self.patch("azure_logging_install.role_setup.time.sleep")
        self.log_mock = self.patch("azure_logging_install.role_setup.log")
        self.config = Configuration(
            control_plane_region=CONTROL_PLANE_REGION,
            control_plane_sub_id="cp-sub",
            control_plane_rg=CONTROL_PLANE_RESOURCE_GROUP,
            monitored_subs="mon-1",
            datadog_api_key="key",
        )

    def patch(self, path: str, **kwargs):
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def _deleting_json(self) -> str:
        return json.dumps({"properties": {"provisioningState": "Deleting"}})

    def test_not_found_returns_immediately(self):
        self.execute_mock.side_effect = ResourceGroupNotFoundError("not found")
        ensure_control_plane_rg_not_deleting(self.config, ["sub-a"])
        self.execute_mock.assert_called_once()
        self.sleep_mock.assert_not_called()

    def test_deleting_then_not_found(self):
        self.execute_mock.side_effect = [
            self._deleting_json(),
            ResourceGroupNotFoundError("gone"),
        ]
        ensure_control_plane_rg_not_deleting(self.config, ["sub-a"])
        self.assertEqual(self.execute_mock.call_count, 2)
        self.sleep_mock.assert_called_once()

    def test_deleting_three_times_raises(self):
        self.execute_mock.return_value = self._deleting_json()
        with self.assertRaises(ResourceGroupDeletionWaitTimeoutError) as ctx:
            ensure_control_plane_rg_not_deleting(self.config, ["sub-a"])
        self.assertIn(CONTROL_PLANE_RESOURCE_GROUP, str(ctx.exception))
        self.assertIn("sub-a", str(ctx.exception))
        self.assertEqual(self.execute_mock.call_count, 3)
        self.assertEqual(self.sleep_mock.call_count, 2)
