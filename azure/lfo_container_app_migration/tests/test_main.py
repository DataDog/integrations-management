# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

from unittest import TestCase
from unittest.mock import patch as mock_patch

from azure_lfo_container_app_migration.main import run_migration

from caj_migration.tests.test_data import (
    CONTROL_PLANE_ID,
    make_function_app_control_plane,
)


class TestRunMigration(TestCase):
    def setUp(self) -> None:
        self.mock_validate_az_cli = self.patch("azure_lfo_container_app_migration.main.validate_az_cli")
        self.mock_find_candidates = self.patch("azure_lfo_container_app_migration.main.find_migration_candidates")
        self.mock_confirm = self.patch("azure_lfo_container_app_migration.main.confirm_yes_no")
        self.mock_migrate_one = self.patch("azure_lfo_container_app_migration.main.migrate_one_installation")

        self.control_plane = make_function_app_control_plane()
        self.mock_find_candidates.return_value = {CONTROL_PLANE_ID: self.control_plane}

    def patch(self, path: str, **kwargs):
        patcher = mock_patch(path, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_no_candidates_does_nothing(self):
        self.mock_find_candidates.return_value = {}

        run_migration(None, skip_confirmation=False)

        self.mock_migrate_one.assert_not_called()

    def test_prompts_by_default_and_migrates_on_confirmation(self):
        self.mock_confirm.return_value = True

        run_migration(None, skip_confirmation=False)

        self.mock_confirm.assert_called_once()
        self.mock_migrate_one.assert_called_once_with(self.control_plane)

    def test_prompt_declined_skips_migration(self):
        self.mock_confirm.return_value = False

        run_migration(None, skip_confirmation=False)

        self.mock_migrate_one.assert_not_called()

    def test_yes_flag_skips_prompt(self):
        run_migration(None, skip_confirmation=True)

        self.mock_confirm.assert_not_called()
        self.mock_migrate_one.assert_called_once_with(self.control_plane)

    def test_explicit_control_plane_ids_skip_prompt(self):
        run_migration(CONTROL_PLANE_ID, skip_confirmation=False)

        self.mock_confirm.assert_not_called()
        self.mock_migrate_one.assert_called_once_with(self.control_plane)
        self.mock_find_candidates.assert_called_once_with({CONTROL_PLANE_ID})

    def test_explicit_control_plane_ids_are_parsed_as_a_comma_separated_set(self):
        run_migration(f"{CONTROL_PLANE_ID}, other-id ", skip_confirmation=False)

        self.mock_find_candidates.assert_called_once_with({CONTROL_PLANE_ID, "other-id"})

    def test_failure_on_one_installation_does_not_prevent_others(self):
        other_control_plane = make_function_app_control_plane()
        self.mock_find_candidates.return_value = {
            CONTROL_PLANE_ID: self.control_plane,
            "other-id": other_control_plane,
        }
        self.mock_migrate_one.side_effect = [RuntimeError("boom"), None]

        run_migration(None, skip_confirmation=True)

        self.assertEqual(self.mock_migrate_one.call_count, 2)
