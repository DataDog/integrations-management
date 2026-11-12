# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase
from unittest.mock import patch as mock_patch

from az_shared.errors import ResourceNotFoundError
from azure_logging_install.configuration import Configuration, ControlPlane, ControlPlaneType

from azure_lfo_container_app_migration.migration import migrate_control_plane, run_migration

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
        run_migration(set(), skip_confirmation=True, dry_run=False)

        self.assertEqual([c.args[0].id for c in self.migrate_mock.call_args_list], ["aaa111", "bbb222"])

    def test_control_plane_ids_filter_restricts_to_the_matching_control_plane(self):
        run_migration({"bbb222"}, skip_confirmation=True, dry_run=False)

        self.migrate_mock.assert_called_once()
        self.assertEqual(self.migrate_mock.call_args.args[0].id, "bbb222")

    def test_unknown_control_plane_id_migrates_nothing(self):
        run_migration({"unknown-id"}, skip_confirmation=True, dry_run=False)

        self.migrate_mock.assert_not_called()

    def test_dry_run_is_the_default(self):
        run_migration({"aaa111"}, skip_confirmation=False)

        self.migrate_mock.assert_called_once_with(self.control_planes[0], True)

    def test_dry_run_does_not_prompt_and_passes_dry_run_through(self):
        confirm_mock = self.patch("azure_lfo_container_app_migration.migration.confirm_yes")

        run_migration({"aaa111"}, skip_confirmation=False, dry_run=True)

        confirm_mock.assert_not_called()
        self.migrate_mock.assert_called_once_with(self.control_planes[0], True)


class TestMigrateControlPlaneDryRun(TestCase):
    def setUp(self) -> None:
        self.control_plane = _control_plane("aaa111")
        self.function_app_config = Configuration(
            control_plane=self.control_plane,
            monitored_subs="sub-1,sub-2",
            datadog_api_key="abcdefgh12345678wxyz",
            resource_tag_filters="env:prod",
            pii_scrubber_rules="secret-rule",
        )
        self.get_config_mock = self.patch(
            "azure_lfo_container_app_migration.migration.get_current_config_for_control_plane",
            return_value=self.function_app_config,
        )
        self.patch("azure_lfo_container_app_migration.migration._verify_function_app_installation")
        self.run_steps_mock = self.patch("azure_lfo_container_app_migration.migration.run_steps")
        self.run_cleanup_steps_mock = self.patch("azure_lfo_container_app_migration.migration.run_cleanup_steps")
        # Read-only lookups made while describing steps
        self.patch(
            "azure_lfo_container_app_migration.create_container_app_job.verify_container_app_job_exists",
            side_effect=ResourceNotFoundError("not found"),
        )
        self.patch("azure_lfo_container_app_migration.grant_permissions.resource_group_exists", return_value=True)

    def patch(self, path: str, **kwargs):
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_dry_run_logs_plan_without_running_any_step(self):
        with self.assertLogs("logging_installer", level="INFO") as logs:
            migrate_control_plane(self.control_plane, dry_run=True)

        self.run_steps_mock.assert_not_called()
        self.run_cleanup_steps_mock.assert_not_called()
        output = "\n".join(logs.output)
        self.assertIn("Monitored subscriptions (2): sub-1, sub-2", output)
        self.assertIn("Datadog API key: set (ending in wxyz)", output)
        self.assertIn("Resource tag filters: env:prod", output)
        self.assertIn("Grant role assignments to Container App Job identities", output)
        self.assertIn("Delete old Function Apps", output)
        # Secrets must not be printed
        self.assertNotIn("abcdefgh12345678wxyz", output)
        self.assertNotIn("secret-rule", output)

    def test_dry_run_warns_when_api_key_or_monitored_subscriptions_missing(self):
        self.get_config_mock.return_value = Configuration(
            control_plane=self.control_plane, monitored_subs="", datadog_api_key=""
        )

        with self.assertLogs("logging_installer", level="WARNING") as logs:
            migrate_control_plane(self.control_plane, dry_run=True)

        output = "\n".join(logs.output)
        self.assertIn("No Datadog API key", output)
        self.assertIn("No monitored subscriptions", output)

    def test_dry_run_repeats_problems_after_the_plan(self):
        self.patch("azure_lfo_container_app_migration.grant_permissions.resource_group_exists", return_value=None)

        with self.assertLogs("logging_installer", level="WARNING") as logs:
            migrate_control_plane(self.control_plane, dry_run=True)

        output = "\n".join(logs.output)
        self.assertIn("Subscription sub-1 could not be checked", output)
        self.assertIn("problem(s) found above. The migration would likely fail and roll back.", output)

    def test_without_dry_run_steps_are_run(self):
        migrate_control_plane(self.control_plane, dry_run=False)

        self.run_steps_mock.assert_called_once()
        self.run_cleanup_steps_mock.assert_called_once()
