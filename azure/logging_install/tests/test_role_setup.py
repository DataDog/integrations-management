# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
from unittest import TestCase
from unittest.mock import MagicMock, call
from unittest.mock import patch as mock_patch

from az_shared.errors import ResourceGroupNotFoundError
from azure_logging_install.configuration import Configuration, ControlPlane, ControlPlaneType
from azure_logging_install.constants import (
    MONITORING_CONTRIBUTOR_ID,
    MONITORING_READER_ID,
    SCALING_CONTRIBUTOR_ID,
    STORAGE_READER_AND_DATA_ACCESS_ID,
)
from azure_logging_install.role_setup import (
    ensure_control_plane_rg_not_deleting,
    grant_subscriptions_permissions,
    revoke_subscriptions_role_assignments,
)

from tests.test_data import (
    CONTROL_PLANE_ID,
    CONTROL_PLANE_REGION,
    CONTROL_PLANE_RESOURCE_GROUP,
)


class TestWaitUntilControlPlaneRgReadyForGrant(TestCase):
    def setUp(self) -> None:
        self.execute_mock = self.patch("azure_logging_install.role_setup.execute")
        self.sleep_mock = self.patch("azure_logging_install.role_setup.time.sleep")
        self.log_mock = self.patch("azure_logging_install.role_setup.log")
        self.config = Configuration(
            control_plane=ControlPlane(
                id=CONTROL_PLANE_ID,
                sub_id="cp-sub",
                resource_group=CONTROL_PLANE_RESOURCE_GROUP,
                region=CONTROL_PLANE_REGION,
                type=ControlPlaneType.FunctionApps,
            ),
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
        ensure_control_plane_rg_not_deleting(CONTROL_PLANE_RESOURCE_GROUP, ["sub-a"])
        self.execute_mock.assert_called_once()
        self.sleep_mock.assert_not_called()

    def test_deleting_then_not_found(self):
        self.execute_mock.side_effect = [
            self._deleting_json(),
            ResourceGroupNotFoundError("gone"),
        ]
        ensure_control_plane_rg_not_deleting(CONTROL_PLANE_RESOURCE_GROUP, ["sub-a"])
        self.assertEqual(self.execute_mock.call_count, 2)
        self.sleep_mock.assert_called_once()
        self.log_mock.info.assert_called_once()

    def test_many_deleting_then_not_found(self):
        n_deleting = 10
        self.execute_mock.side_effect = [self._deleting_json()] * n_deleting + [ResourceGroupNotFoundError("gone")]
        ensure_control_plane_rg_not_deleting(CONTROL_PLANE_RESOURCE_GROUP, ["sub-a"])
        self.assertEqual(self.execute_mock.call_count, n_deleting + 1)
        self.assertEqual(self.sleep_mock.call_count, n_deleting)
        self.log_mock.info.assert_called_once()

    def test_succeeded_breaks_without_sleep(self):
        self.execute_mock.return_value = json.dumps({"properties": {"provisioningState": "Succeeded"}})
        ensure_control_plane_rg_not_deleting(CONTROL_PLANE_RESOURCE_GROUP, ["sub-a"])
        self.execute_mock.assert_called_once()
        self.sleep_mock.assert_not_called()

    def test_callbacks_not_called_when_rg_not_found(self):
        self.execute_mock.side_effect = ResourceGroupNotFoundError("not found")
        on_start = MagicMock()
        ensure_control_plane_rg_not_deleting(CONTROL_PLANE_RESOURCE_GROUP, ["sub-a"], on_start)
        on_start.assert_not_called()

    def test_on_start_called_once_when_deleting(self):
        self.execute_mock.side_effect = [
            self._deleting_json(),
            self._deleting_json(),
            ResourceGroupNotFoundError("gone"),
        ]
        on_start = MagicMock()
        ensure_control_plane_rg_not_deleting(CONTROL_PLANE_RESOURCE_GROUP, ["sub-a"], on_start)
        on_start.assert_called_once()

    def test_on_start_called_once_across_multiple_deleting_subscriptions(self):
        self.execute_mock.side_effect = [
            self._deleting_json(),
            ResourceGroupNotFoundError("gone"),  # sub-a done
            self._deleting_json(),
            ResourceGroupNotFoundError("gone"),  # sub-b done
        ]
        on_start = MagicMock()
        ensure_control_plane_rg_not_deleting(CONTROL_PLANE_RESOURCE_GROUP, ["sub-a", "sub-b"], on_start)
        on_start.assert_called_once()


class TestSubscriptionTaskRoleAssignments(TestCase):
    """Pins the exact role assignments granted and revoked per subscription, so changing them is deliberate."""

    def setUp(self) -> None:
        self.assign_role_mock = self.patch("azure_logging_install.role_setup.assign_role")
        self.remove_role_mock = self.patch("azure_logging_install.role_setup.remove_role")
        self.set_subscription_mock = self.patch("azure_logging_install.role_setup.set_subscription")
        self.ensure_rg_mock = self.patch("azure_logging_install.role_setup._ensure_resource_group_exists")
        self.patch(
            "azure_logging_install.role_setup._get_control_plane_task_principal_ids",
            return_value=("resources-principal", "scaling-principal", "diagnostic-principal"),
        )
        self.control_plane = ControlPlane(
            id=CONTROL_PLANE_ID,
            sub_id="cp-sub",
            resource_group=CONTROL_PLANE_RESOURCE_GROUP,
            region=CONTROL_PLANE_REGION,
            type=ControlPlaneType.ContainerAppJobs,
        )

    def patch(self, path: str, **kwargs):
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def _expected(self, sub_id: str) -> list[tuple[str, str, str]]:
        sub_scope = f"/subscriptions/{sub_id}"
        rg_scope = f"{sub_scope}/resourceGroups/{CONTROL_PLANE_RESOURCE_GROUP}"
        return [
            (sub_scope, "resources-principal", MONITORING_READER_ID),
            (rg_scope, "scaling-principal", SCALING_CONTRIBUTOR_ID),
            (sub_scope, "diagnostic-principal", MONITORING_CONTRIBUTOR_ID),
            (rg_scope, "diagnostic-principal", STORAGE_READER_AND_DATA_ACCESS_ID),
        ]

    def test_grant_assigns_each_task_role_in_every_subscription(self):
        grant_subscriptions_permissions(self.control_plane, ["sub-a", "sub-b"])

        expected = [call(*args, CONTROL_PLANE_ID) for sub in ("sub-a", "sub-b") for args in self._expected(sub)]
        self.assertEqual(self.assign_role_mock.call_args_list, expected)
        self.assertEqual(
            self.ensure_rg_mock.call_args_list,
            [call(CONTROL_PLANE_RESOURCE_GROUP, sub, CONTROL_PLANE_REGION) for sub in ("sub-a", "sub-b")],
        )
        self.assertEqual(self.set_subscription_mock.call_args_list, [call("sub-a"), call("sub-b"), call("cp-sub")])

    def test_revoke_removes_the_same_role_assignments(self):
        revoke_subscriptions_role_assignments(self.control_plane, ["sub-a", "sub-b"])

        expected = [call(*args) for sub in ("sub-a", "sub-b") for args in self._expected(sub)]
        self.assertEqual(self.remove_role_mock.call_args_list, expected)
