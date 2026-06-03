# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
from unittest import TestCase
from unittest.mock import _patch, patch

from azure_lfo_consumption_plan_migration.discovery import discover_control_planes


class TestDiscoverControlPlanes(TestCase):
    def _patch_execute(self, graph_response: dict) -> "_patch":
        def fake_execute(cmd, can_fail=False):
            cmd_str = str(cmd)
            if "extension show" in cmd_str:
                return "installed"
            if "graph query" in cmd_str:
                # Capture the query so tests can inspect it.
                fake_execute.last_cmd = cmd_str  # type: ignore[attr-defined]
                return json.dumps(graph_response)
            return ""

        return patch(
            "azure_lfo_consumption_plan_migration.discovery.execute",
            side_effect=fake_execute,
        )

    def test_parses_control_plane_id_from_function_app_name(self) -> None:
        response = {
            "data": [
                {
                    "name": "resources-task-aabbccddeeff",
                    "resourceGroup": "datadog_control_plane",
                    "subscriptionId": "sub-1",
                    "location": "eastus",
                }
            ]
        }
        with self._patch_execute(response):
            results = discover_control_planes()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].control_plane_id, "aabbccddeeff")
        self.assertEqual(results[0].sub_id, "sub-1")
        self.assertEqual(results[0].resource_group, "datadog_control_plane")
        self.assertEqual(results[0].region, "eastus")

    def test_subscription_filter_adds_clause(self) -> None:
        response: dict = {"data": []}
        with self._patch_execute(response) as exec_mock:
            discover_control_planes(subscription_filter="sub-xyz")
        captured = " ".join(c.args[0].__str__() for c in exec_mock.call_args_list)
        self.assertIn("sub-xyz", captured)

    def test_control_plane_id_filter_adds_clause(self) -> None:
        response: dict = {"data": []}
        with self._patch_execute(response) as exec_mock:
            discover_control_planes(control_plane_id_filter="aabbccddeeff")
        captured = " ".join(c.args[0].__str__() for c in exec_mock.call_args_list)
        self.assertIn("aabbccddeeff", captured)

    def test_empty_response_returns_empty_list(self) -> None:
        with self._patch_execute({"data": []}):
            results = discover_control_planes()
        self.assertEqual(results, [])
