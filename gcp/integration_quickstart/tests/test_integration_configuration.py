# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import unittest
from unittest.mock import Mock, call, patch

from gcp_integration_quickstart.integration_configuration import (
    ROLE_TO_REQUIRED_API,
    ROLES_TO_ADD,
    assign_delegate_permissions,
    create_integration_with_permissions,
    find_or_create_service_account,
)
from gcp_integration_quickstart.models import (
    ConfigurationScope,
    Folder,
    IntegrationConfiguration,
    Project,
)


class TestFindOrCreateServiceAccount(unittest.TestCase):
    """Test the find_or_create_service_account function."""

    @patch("gcp_integration_quickstart.integration_configuration.gcloud")
    def test_find_or_create_service_account_existing(self, mock_gcloud):
        """Test find_or_create_service_account when service account already exists."""
        mock_gcloud.return_value = [{"email": "test@project.iam.gserviceaccount.com"}]

        # Create a mock step reporter
        step_reporter = Mock()

        result = find_or_create_service_account(
            step_reporter, "test-account", "test-project"
        )

        mock_gcloud.assert_called_once_with(
            "iam service-accounts list             --project=test-project              --filter=\"email~'test-account'\"",
            "email",
        )
        self.assertEqual(result, "test@project.iam.gserviceaccount.com")

    @patch("gcp_integration_quickstart.integration_configuration.gcloud")
    def test_find_or_create_service_account_new(self, mock_gcloud):
        """Test find_or_create_service_account when creating new service account."""
        # First call returns empty list (no existing account)
        # Second call returns the created account
        mock_gcloud.side_effect = [
            [],
            {"email": "test-account@test-project.iam.gserviceaccount.com"},
        ]

        # Create a mock step reporter
        step_reporter = Mock()

        result = find_or_create_service_account(
            step_reporter, "test-account", "test-project"
        )

        expected_calls = [
            call(
                "iam service-accounts list             --project=test-project              --filter=\"email~'test-account'\"",
                "email",
            ),
            call(
                'iam service-accounts create test-account             --display-name="Datadog Service Account"            --project=test-project',
                "email",
            ),
        ]

        mock_gcloud.assert_has_calls(expected_calls)
        self.assertEqual(result, "test-account@test-project.iam.gserviceaccount.com")


class TestAssignDelegatePermissions(unittest.TestCase):
    """Test the assign_delegate_permissions function."""

    @patch("gcp_integration_quickstart.integration_configuration.gcloud")
    @patch("gcp_integration_quickstart.integration_configuration.dd_request")
    def test_assign_delegate_permissions_success(self, mock_dd_request, mock_gcloud):
        """Test assign_delegate_permissions when successful."""

        # Mock dd_request response for STS delegate
        mock_dd_request.return_value = (
            json.dumps(
                {
                    "data": {
                        "id": "datadog-service-account@datadog.iam.gserviceaccount.com"
                    }
                }
            ),
            200,
        )

        mock_gcloud.return_value = None

        # Create a mock step reporter
        step_reporter = Mock()

        assign_delegate_permissions(step_reporter, "test-project")

        # Verify dd_request was called for STS delegate
        mock_dd_request.assert_called_once_with(
            "GET", "/api/v2/integration/gcp/sts_delegate"
        )

        # Verify gcloud was called with the correct command
        mock_gcloud.assert_called_once_with(
            'projects add-iam-policy-binding "test-project"                 --member="serviceAccount:datadog-service-account@datadog.iam.gserviceaccount.com"                 --role="roles/iam.serviceAccountTokenCreator"                 --condition=None                 --quiet                 '
        )

    @patch("gcp_integration_quickstart.integration_configuration.dd_request")
    def test_assign_delegate_permissions_sts_failure(self, mock_dd_request):
        """Test assign_delegate_permissions when STS delegate request fails."""

        # Mock dd_request response for STS delegate failure
        mock_dd_request.return_value = ('{"error": "not found"}', 404)

        # Create a mock step reporter
        step_reporter = Mock()

        with self.assertRaises(RuntimeError) as context:
            assign_delegate_permissions(step_reporter, "test-project")

        self.assertIn("failed to get sts delegate", str(context.exception))


class TestCreateIntegrationWithPermissions(unittest.TestCase):
    """Test the create_integration_with_permissions function."""

    def setUp(self):
        """Set up test fixtures."""
        self.service_account = (
            "test-service-account@test-project.iam.gserviceaccount.com"
        )
        self.integration_configuration = IntegrationConfiguration(
            metric_namespace_configs=[{"namespace": "test"}],
            monitored_resource_configs=[{"cloud_run": ["filter1"]}],
            account_tags=["tag1", "tag2"],
            resource_collection_enabled=True,
            automute=False,
        )

    @patch("gcp_integration_quickstart.integration_configuration.gcloud")
    @patch("gcp_integration_quickstart.integration_configuration.dd_request")
    def test_create_integration_with_permissions_success(
        self, mock_dd_request, mock_gcloud
    ):
        """Test create_integration_with_permissions when successful."""

        # Mock dd_request response for integration creation
        mock_dd_request.return_value = ('{"status": "ok"}', 201)

        mock_gcloud.return_value = None

        # Create a mock step reporter
        step_reporter = Mock()

        # Create test configuration scope
        child_project = Project(
            parent_id="folder123",
            id="child-project123",
            name="Child Project",
            is_already_monitored=False,
        )

        folder = Folder(
            parent_id="parent123",
            id="folder123",
            name="Test Folder",
            child_scopes=[child_project],
        )

        project = Project(
            parent_id="parent456",
            id="project123",
            name="Test Project",
            is_already_monitored=False,
        )

        configuration_scope = ConfigurationScope(projects=[project], folders=[folder])

        create_integration_with_permissions(
            step_reporter,
            self.service_account,
            self.integration_configuration,
            configuration_scope,
        )

        # Verify gcloud calls for folder child projects
        expected_gcloud_calls = []

        # Calls for child project APIs (all services in one call)
        services_to_enable = " ".join(ROLE_TO_REQUIRED_API.values())
        expected_gcloud_calls.append(
            call(
                f"services enable {services_to_enable} \
                --project=child-project123 \
                --quiet"
            )
        )

        # Calls for folder roles
        for role in ROLES_TO_ADD:
            expected_gcloud_calls.append(
                call(
                    f'resource-manager folders add-iam-policy-binding "folder123" \
                --member="serviceAccount:{self.service_account}" \
                --role="{role}" \
                --condition=None \
                --quiet \
                '
                )
            )

        # Calls for project APIs (all services in one call)
        expected_gcloud_calls.append(
            call(
                f"services enable {services_to_enable} \
               --project=project123 \
               --quiet"
            )
        )

        # Calls for project roles
        for role in ROLES_TO_ADD:
            expected_gcloud_calls.append(
                call(
                    f'projects add-iam-policy-binding "project123" \
                --member="serviceAccount:{self.service_account}" \
                --role="{role}" \
                --condition=None \
                --quiet \
                '
                )
            )

        mock_gcloud.assert_has_calls(expected_gcloud_calls)

        mock_dd_request.assert_called_once_with(
            "POST",
            "/api/v2/integration/gcp/accounts?source=script",
            {
                "data": {
                    "type": "gcp_service_account",
                    "attributes": {
                        "client_email": self.service_account,
                        "is_per_project_quota_enabled": True,
                        "metric_namespace_configs": [{"namespace": "test"}],
                        "monitored_resource_configs": [{"cloud_run": ["filter1"]}],
                        "account_tags": ["tag1", "tag2"],
                        "resource_collection_enabled": True,
                        "automute": False,
                    },
                }
            },
        )

    @patch("gcp_integration_quickstart.integration_configuration.gcloud")
    @patch("gcp_integration_quickstart.integration_configuration.dd_request")
    def test_create_integration_with_permissions_integration_creation_failure(
        self, mock_dd_request, mock_gcloud
    ):
        """Test create_integration_with_permissions when integration creation fails."""

        # Mock dd_request response for integration creation failure
        mock_dd_request.return_value = ('{"error": "bad request"}', 400)

        mock_gcloud.return_value = None

        # Create a mock step reporter
        step_reporter = Mock()

        configuration_scope = ConfigurationScope(projects=[], folders=[])

        with self.assertRaises(RuntimeError) as context:
            create_integration_with_permissions(
                step_reporter,
                self.service_account,
                self.integration_configuration,
                configuration_scope,
            )

        self.assertIn("failed to create service account", str(context.exception))


if __name__ == "__main__":
    unittest.main()
