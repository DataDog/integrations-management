# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import unittest
from unittest.mock import MagicMock, patch

from gcp_shared.service_accounts import (
    find_or_create_service_account,
    find_service_account,
)


class TestFindServiceAccount(unittest.TestCase):
    """Test the find_service_account function."""

    @patch("gcp_shared.service_accounts.gcloud")
    def test_find_service_account_found(self, mock_gcloud):
        """Test finding an existing service account."""
        mock_gcloud.return_value = [
            {"email": "test-account@project-id.iam.gserviceaccount.com"}
        ]

        result = find_service_account("test-account", "project-id")

        self.assertEqual(
            result, "test-account@project-id.iam.gserviceaccount.com"
        )
        mock_gcloud.assert_called_once()
        # Check the GcloudCmd object by converting to string
        call_args = mock_gcloud.call_args[0]
        cmd_str = str(call_args[0])
        self.assertIn("iam", cmd_str)
        self.assertIn("service-accounts", cmd_str)
        self.assertIn("list", cmd_str)
        self.assertIn("--project", cmd_str)
        self.assertIn("project-id", cmd_str)
        self.assertIn("--filter", cmd_str)
        self.assertIn("test-account", cmd_str)
        self.assertEqual(call_args[1], "email")

    @patch("gcp_shared.service_accounts.gcloud")
    def test_find_service_account_not_found(self, mock_gcloud):
        """Test when service account is not found."""
        mock_gcloud.return_value = []

        result = find_service_account("nonexistent", "project-id")

        self.assertIsNone(result)

    @patch("gcp_shared.service_accounts.gcloud")
    def test_find_service_account_returns_none(self, mock_gcloud):
        """Test when gcloud returns None."""
        mock_gcloud.return_value = None

        result = find_service_account("test-account", "project-id")

        self.assertIsNone(result)

    @patch("gcp_shared.service_accounts.gcloud")
    def test_find_service_account_multiple_results(self, mock_gcloud):
        """Test when multiple service accounts match (returns first)."""
        mock_gcloud.return_value = [
            {"email": "test-account-1@project.iam.gserviceaccount.com"},
            {"email": "test-account-2@project.iam.gserviceaccount.com"}
        ]

        result = find_service_account("test-account", "project-id")

        self.assertEqual(
            result, "test-account-1@project.iam.gserviceaccount.com"
        )


class TestFindOrCreateServiceAccount(unittest.TestCase):
    """Test the find_or_create_service_account function."""

    @patch("gcp_shared.service_accounts.gcloud")
    def test_find_or_create_finds_existing(self, mock_gcloud):
        """Test when service account already exists."""
        step_reporter = MagicMock()
        mock_gcloud.return_value = [
            {"email": "existing@project-id.iam.gserviceaccount.com"}
        ]

        result = find_or_create_service_account(
            step_reporter, "existing", "project-id"
        )

        self.assertEqual(
            result, "existing@project-id.iam.gserviceaccount.com"
        )
        # Should be called once for the search
        self.assertEqual(mock_gcloud.call_count, 1)
        # Should report looking for and finding the account
        self.assertEqual(step_reporter.report.call_count, 2)
        self.assertIn(
            "Looking for", step_reporter.report.call_args_list[0][1]["message"]
        )
        self.assertIn(
            "Found existing",
            step_reporter.report.call_args_list[1][1]["message"]
        )

    @patch("gcp_shared.service_accounts.gcloud")
    def test_find_or_create_creates_new(self, mock_gcloud):
        """Test creating a new service account."""
        step_reporter = MagicMock()
        # First call (search) returns empty, second call (create) returns new
        mock_gcloud.side_effect = [
            [],  # find returns nothing
            {"email": "new-account@project-id.iam.gserviceaccount.com"}
        ]

        result = find_or_create_service_account(
            step_reporter, "new-account", "project-id"
        )

        self.assertEqual(
            result, "new-account@project-id.iam.gserviceaccount.com"
        )
        # Should be called twice: once for search, once for create
        self.assertEqual(mock_gcloud.call_count, 2)
        # Should report looking, and creating
        self.assertEqual(step_reporter.report.call_count, 2)
        self.assertIn(
            "Looking for", step_reporter.report.call_args_list[0][1]["message"]
        )
        self.assertIn(
            "Creating new",
            step_reporter.report.call_args_list[1][1]["message"]
        )

    @patch("gcp_shared.service_accounts.gcloud")
    def test_find_or_create_custom_display_name(self, mock_gcloud):
        """Test creating with custom display name."""
        step_reporter = MagicMock()
        mock_gcloud.side_effect = [
            [],  # find returns nothing
            {"email": "custom@project-id.iam.gserviceaccount.com"}
        ]

        result = find_or_create_service_account(
            step_reporter,
            "custom",
            "project-id",
            "Custom Display Name"
        )

        self.assertEqual(
            result, "custom@project-id.iam.gserviceaccount.com"
        )
        # Check that the create call includes the custom display name
        create_call = mock_gcloud.call_args_list[1]
        cmd_str = str(create_call[0][0])
        self.assertIn("Custom Display Name", cmd_str)

    @patch("gcp_shared.service_accounts.gcloud")
    def test_find_or_create_default_display_name(self, mock_gcloud):
        """Test creating with default display name."""
        step_reporter = MagicMock()
        mock_gcloud.side_effect = [
            [],  # find returns nothing
            {"email": "default@project-id.iam.gserviceaccount.com"}
        ]

        result = find_or_create_service_account(
            step_reporter, "default", "project-id"
        )

        self.assertEqual(
            result, "default@project-id.iam.gserviceaccount.com"
        )
        # Check that the create call includes the default display name
        create_call = mock_gcloud.call_args_list[1]
        cmd_str = str(create_call[0][0])
        self.assertIn("Datadog Service Account", cmd_str)

    @patch("gcp_shared.service_accounts.gcloud")
    def test_find_or_create_reports_correctly(self, mock_gcloud):
        """Test that status reports are sent correctly."""
        step_reporter = MagicMock()
        mock_gcloud.side_effect = [
            None,  # find returns None
            {"email": "new@project-id.iam.gserviceaccount.com"}
        ]

        find_or_create_service_account(
            step_reporter, "new", "my-project"
        )

        # Verify the correct messages were reported
        calls = step_reporter.report.call_args_list
        self.assertEqual(len(calls), 2)

        # First message should be about looking for the account
        first_message = calls[0][1]["message"]
        self.assertIn("Looking for", first_message)
        self.assertIn("new", first_message)
        self.assertIn("my-project", first_message)

        # Second message should be about creating the account
        second_message = calls[1][1]["message"]
        self.assertIn("Creating new", second_message)
        self.assertIn("new", second_message)
        self.assertIn("my-project", second_message)


if __name__ == "__main__":
    unittest.main()
