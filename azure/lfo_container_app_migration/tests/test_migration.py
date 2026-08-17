# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase
from unittest.mock import patch as mock_patch

from azure_logging_install.configuration import ControlPlane, ControlPlaneType

from azure_lfo_container_app_migration.migration import run_migration

SUBSCRIPTION_ID = "test-sub"
RESOURCE_GROUP = "test-rg"
REGION = "eastus"


def _control_plane(control_plane_id: str) -> ControlPlane:
    return ControlPlane(
        id=control_plane_id,
        sub_id=SUBSCRIPTION_ID,
        resource_group=RESOURCE_GROUP,
        region=REGION,
        type=ControlPlaneType.FunctionApps,
    )


class TestRunMigration(TestCase):
    def setUp(self) -> None:
        self.control_planes = [_control_plane("aaa111"), _control_plane("bbb222")]
        self.find_mock = self.patch(
            "azure_lfo_container_app_migration.migration.find_existing_lfo_control_planes", return_value=self.control_planes
        )
        self.migrate_mock = self.patch("azure_lfo_container_app_migration.migration.migrate_control_plane")

    def patch(self, path: str, **kwargs):
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_no_filter_migrates_every_discovered_control_plane(self):
        run_migration(set(), skip_confirmation=True)

        self.assertEqual([c.args[0].id for c in self.migrate_mock.call_args_list], ["aaa111", "bbb222"])

    def test_control_plane_ids_filter_restricts_to_the_matching_control_plane(self):
        run_migration({"bbb222"}, skip_confirmation=True)

        self.migrate_mock.assert_called_once()
        self.assertEqual(self.migrate_mock.call_args.args[0].id, "bbb222")

    def test_unknown_control_plane_id_migrates_nothing(self):
        run_migration({"unknown-id"}, skip_confirmation=True)

        self.migrate_mock.assert_not_called()
