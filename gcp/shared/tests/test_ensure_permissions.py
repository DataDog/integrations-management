# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import unittest
from unittest.mock import Mock, patch

from gcp_shared.ensure_permissions import (
    create_service_account_with_permissions,
    ensure_service_account_permissions,
    is_valid_service_account_email,
    validate_service_account_in_project,
)


class TestIsValidServiceAccountEmail(unittest.TestCase):
    def test_valid_email(self):
        self.assertTrue(is_valid_service_account_email("my-sa@my-project.iam.gserviceaccount.com"))

    def test_invalid_email_plain_string(self):
        self.assertFalse(is_valid_service_account_email("not-an-email"))

    def test_invalid_email_wrong_domain(self):
        self.assertFalse(is_valid_service_account_email("sa@gmail.com"))

    def test_invalid_email_missing_iam_segment(self):
        self.assertFalse(is_valid_service_account_email("sa@project.gserviceaccount.com"))

    def test_invalid_email_empty_string(self):
        self.assertFalse(is_valid_service_account_email(""))

    def test_invalid_email_single_quote_in_local_part(self):
        self.assertFalse(is_valid_service_account_email("o'brien@proj.iam.gserviceaccount.com"))

    def test_invalid_email_uppercase_characters(self):
        self.assertFalse(is_valid_service_account_email("My-SA@my-project.iam.gserviceaccount.com"))

    def test_invalid_email_local_part_starts_with_digit(self):
        self.assertFalse(is_valid_service_account_email("1sa@my-project.iam.gserviceaccount.com"))


class TestValidateServiceAccountInProject(unittest.TestCase):
    @patch("gcp_shared.ensure_permissions.gcloud")
    def test_found_does_not_raise(self, mock_gcloud):
        mock_gcloud.return_value = [{"email": "sa@proj.iam.gserviceaccount.com"}]
        step_reporter = Mock()

        validate_service_account_in_project(step_reporter, "sa@proj.iam.gserviceaccount.com", "proj")

        actual_command = str(mock_gcloud.call_args[0][0])
        self.assertIn("iam service-accounts list", actual_command)
        self.assertIn("proj", actual_command)

    @patch("gcp_shared.ensure_permissions.gcloud")
    def test_not_found_raises_runtime_error(self, mock_gcloud):
        mock_gcloud.return_value = []
        step_reporter = Mock()

        with self.assertRaises(RuntimeError) as ctx:
            validate_service_account_in_project(step_reporter, "sa@proj.iam.gserviceaccount.com", "proj")

        self.assertIn("not found", str(ctx.exception))
        self.assertIn("sa@proj.iam.gserviceaccount.com", str(ctx.exception))


class TestEnsureServiceAccountPermissions(unittest.TestCase):
    @patch("gcp_shared.ensure_permissions.gcloud")
    def test_applies_all_roles_after_validating(self, mock_gcloud):
        mock_gcloud.return_value = [{"email": "sa@proj.iam.gserviceaccount.com"}]
        step_reporter = Mock()
        roles = ["roles/browser", "roles/compute.viewer"]

        ensure_service_account_permissions(step_reporter, "proj", "sa@proj.iam.gserviceaccount.com", roles)

        # 1 validate call + 1 per role
        self.assertEqual(mock_gcloud.call_count, 3)
        bind_calls = [str(c[0][0]) for c in mock_gcloud.call_args_list[1:]]
        self.assertTrue(any("roles/browser" in cmd for cmd in bind_calls))
        self.assertTrue(any("roles/compute.viewer" in cmd for cmd in bind_calls))

    @patch("gcp_shared.ensure_permissions.gcloud")
    def test_raises_when_sa_not_found(self, mock_gcloud):
        mock_gcloud.return_value = []
        step_reporter = Mock()

        with self.assertRaises(RuntimeError):
            ensure_service_account_permissions(
                step_reporter, "proj", "missing@proj.iam.gserviceaccount.com", ["roles/browser"]
            )

        # No bind calls should have been made
        self.assertEqual(mock_gcloud.call_count, 1)

    @patch("gcp_shared.ensure_permissions.gcloud")
    def test_no_roles_only_validates(self, mock_gcloud):
        mock_gcloud.return_value = [{"email": "sa@proj.iam.gserviceaccount.com"}]
        step_reporter = Mock()

        ensure_service_account_permissions(step_reporter, "proj", "sa@proj.iam.gserviceaccount.com", [])

        self.assertEqual(mock_gcloud.call_count, 1)


class TestCreateServiceAccountWithPermissions(unittest.TestCase):
    @patch("gcp_shared.ensure_permissions.gcloud")
    @patch("gcp_shared.ensure_permissions.find_or_create_service_account")
    def test_creates_sa_and_applies_roles(self, mock_create_sa, mock_gcloud):
        mock_create_sa.return_value = "new-sa@proj.iam.gserviceaccount.com"
        mock_gcloud.return_value = None
        step_reporter = Mock()
        roles = ["roles/browser", "roles/monitoring.viewer"]

        result = create_service_account_with_permissions(step_reporter, "proj", "new-sa", roles)

        mock_create_sa.assert_called_once_with(step_reporter, "new-sa", "proj", "Datadog Service Account")
        self.assertEqual(result, "new-sa@proj.iam.gserviceaccount.com")
        self.assertEqual(mock_gcloud.call_count, 2)

    @patch("gcp_shared.ensure_permissions.gcloud")
    @patch("gcp_shared.ensure_permissions.find_or_create_service_account")
    def test_uses_custom_display_name(self, mock_create_sa, mock_gcloud):
        mock_create_sa.return_value = "sa@proj.iam.gserviceaccount.com"
        mock_gcloud.return_value = None
        step_reporter = Mock()

        create_service_account_with_permissions(
            step_reporter, "proj", "sa", [], display_name="Custom Name"
        )

        mock_create_sa.assert_called_once_with(step_reporter, "sa", "proj", "Custom Name")

    @patch("gcp_shared.ensure_permissions.gcloud")
    @patch("gcp_shared.ensure_permissions.find_or_create_service_account")
    def test_bind_commands_target_correct_project(self, mock_create_sa, mock_gcloud):
        mock_create_sa.return_value = "sa@my-proj.iam.gserviceaccount.com"
        mock_gcloud.return_value = None
        step_reporter = Mock()

        create_service_account_with_permissions(step_reporter, "my-proj", "sa", ["roles/browser"])

        actual_command = str(mock_gcloud.call_args[0][0])
        self.assertIn("projects add-iam-policy-binding my-proj", actual_command)
        self.assertIn("roles/browser", actual_command)
        self.assertIn("--condition None", actual_command)


if __name__ == "__main__":
    unittest.main()
