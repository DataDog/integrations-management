# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import unittest
from unittest.mock import Mock, patch

from gcp_integration_quickstart.integration_configuration import (
    REQUIRED_APIS,
    REQUIRED_ROLES,
    assign_delegate_permissions,
    create_integration_with_permissions,
)
from gcp_integration_quickstart.models import (
    IntegrationConfiguration,
    ProductRequirements,
)
from gcp_shared.models import (
    ConfigurationScope,
    Folder,
    Project,
)
from gcp_shared.service_accounts import find_or_create_service_account


class TestFindOrCreateServiceAccount(unittest.TestCase):
    """Test the find_or_create_service_account function."""

    @patch("gcp_shared.service_accounts.gcloud")
    def test_find_or_create_service_account_existing(self, mock_gcloud):
        """Test find_or_create_service_account when service account already exists."""
        mock_gcloud.return_value = [{"email": "test@project.iam.gserviceaccount.com"}]

        step_reporter = Mock()

        result = find_or_create_service_account(
            step_reporter, "test-account", "test-project"
        )

        actual_commands = [str(call[0][0]) for call in mock_gcloud.call_args_list]

        self.assertEqual(len(actual_commands), 1)
        self.assertEqual(
            actual_commands[0],
            "iam service-accounts list --project test-project '--filter=email~'\"'\"'test-account'\"'\"''",
        )
        self.assertEqual(result, "test@project.iam.gserviceaccount.com")

    @patch("gcp_shared.service_accounts.gcloud")
    def test_find_or_create_service_account_new(self, mock_gcloud):
        """Test find_or_create_service_account when creating new service account."""
        mock_gcloud.side_effect = [
            [],
            {"email": "test-account@test-project.iam.gserviceaccount.com"},
        ]

        step_reporter = Mock()

        result = find_or_create_service_account(
            step_reporter, "test-account", "test-project"
        )

        actual_commands = [str(call[0][0]) for call in mock_gcloud.call_args_list]

        self.assertEqual(len(actual_commands), 2)
        self.assertEqual(
            actual_commands[0],
            "iam service-accounts list --project test-project '--filter=email~'\"'\"'test-account'\"'\"''",
        )
        self.assertEqual(
            actual_commands[1],
            "iam service-accounts create test-account --display-name 'Datadog Service Account' --project test-project",
        )
        self.assertEqual(result, "test-account@test-project.iam.gserviceaccount.com")


class TestAssignDelegatePermissions(unittest.TestCase):
    """Test the assign_delegate_permissions function."""

    @patch("gcp_integration_quickstart.integration_configuration.gcloud")
    @patch("gcp_integration_quickstart.integration_configuration.dd_request")
    def test_assign_delegate_permissions_success(self, mock_dd_request, mock_gcloud):
        """Test assign_delegate_permissions when successful."""

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

        step_reporter = Mock()

        assign_delegate_permissions(
            step_reporter,
            "test-sa@test-project.iam.gserviceaccount.com",
            "test-project",
        )

        mock_dd_request.assert_called_once_with(
            "GET", "/api/v2/integration/gcp/sts_delegate"
        )

        actual_commands = [str(call[0][0]) for call in mock_gcloud.call_args_list]

        self.assertEqual(len(actual_commands), 1)
        self.assertEqual(
            actual_commands[0],
            "iam service-accounts add-iam-policy-binding test-sa@test-project.iam.gserviceaccount.com --member serviceAccount:datadog-service-account@datadog.iam.gserviceaccount.com --role roles/iam.serviceAccountTokenCreator --condition None --project test-project --quiet",
        )

    @patch("gcp_integration_quickstart.integration_configuration.dd_request")
    def test_assign_delegate_permissions_sts_failure(self, mock_dd_request):
        """Test assign_delegate_permissions when STS delegate request fails."""

        mock_dd_request.return_value = ('{"error": "not found"}', 404)

        step_reporter = Mock()

        with self.assertRaises(RuntimeError) as context:
            assign_delegate_permissions(
                step_reporter,
                "test-sa@test-project.iam.gserviceaccount.com",
                "test-project",
            )

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
            region_filter_configs=["lushy", "boo_boi"],
            is_global_location_enabled=True,
        )

    @patch("gcp_integration_quickstart.integration_configuration.gcloud")
    @patch("gcp_integration_quickstart.integration_configuration.dd_request")
    def test_create_integration_with_permissions_success(
        self, mock_dd_request, mock_gcloud
    ):
        """Test create_integration_with_permissions when successful."""

        mock_dd_request.return_value = ('{"status": "ok"}', 201)

        mock_gcloud.return_value = None

        step_reporter = Mock()

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

        actual_commands = [str(call[0][0]) for call in mock_gcloud.call_args_list]

        expected_commands = []

        services_str = " ".join(REQUIRED_APIS)

        expected_commands.append(
            f"services enable {services_str} --project child-project123 --quiet"
        )

        for role in REQUIRED_ROLES:
            expected_commands.append(
                f"resource-manager folders add-iam-policy-binding folder123 --member serviceAccount:{self.service_account} --role {role} --condition None --quiet"
            )

        expected_commands.append(
            f"services enable {services_str} --project project123 --quiet"
        )

        for role in REQUIRED_ROLES:
            expected_commands.append(
                f"projects add-iam-policy-binding project123 --member serviceAccount:{self.service_account} --role {role} --condition None --quiet"
            )

        self.assertEqual(len(actual_commands), len(expected_commands))
        for i, (actual, expected) in enumerate(zip(actual_commands, expected_commands)):
            self.assertEqual(actual, expected, f"Command {i} mismatch")

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
                        "region_filter_configs": ["lushy", "boo_boi"],
                        "is_global_location_enabled": True,
                    },
                }
            },
        )

    @patch("gcp_integration_quickstart.integration_configuration.gcloud")
    @patch("gcp_integration_quickstart.integration_configuration.dd_request")
    def test_create_integration_with_permissions_with_product_requirements(
        self, mock_dd_request, mock_gcloud
    ):
        """Test create_integration_with_permissions with additional product requirements."""

        mock_dd_request.return_value = ('{"status": "ok"}', 201)

        mock_gcloud.return_value = None

        step_reporter = Mock()

        project = Project(
            parent_id="parent456",
            id="project123",
            name="Test Project",
            is_already_monitored=False,
        )

        configuration_scope = ConfigurationScope(projects=[project], folders=[])

        additional_required_apis = ["additional-api.googleapis.com"]
        additional_required_roles = ["roles/additional.role"]

        product_requirements = ProductRequirements(
            required_apis=additional_required_apis,
            required_roles=additional_required_roles,
        )

        create_integration_with_permissions(
            step_reporter,
            self.service_account,
            self.integration_configuration,
            configuration_scope,
            product_requirements,
        )

        actual_commands = [str(call[0][0]) for call in mock_gcloud.call_args_list]

        expected_commands = []

        all_services = REQUIRED_APIS + additional_required_apis
        services_str = " ".join(all_services)

        expected_commands.append(
            f"services enable {services_str} --project project123 --quiet"
        )

        all_roles = REQUIRED_ROLES + additional_required_roles
        for role in all_roles:
            expected_commands.append(
                f"projects add-iam-policy-binding project123 --member serviceAccount:{self.service_account} --role {role} --condition None --quiet"
            )

        self.assertEqual(len(actual_commands), len(expected_commands))
        for i, (actual, expected) in enumerate(zip(actual_commands, expected_commands)):
            self.assertEqual(actual, expected, f"Command {i} mismatch")

        mock_dd_request.assert_called_once()

    @patch("gcp_integration_quickstart.integration_configuration.gcloud")
    @patch("gcp_integration_quickstart.integration_configuration.dd_request")
    def test_create_integration_with_permissions_integration_creation_failure(
        self, mock_dd_request, mock_gcloud
    ):
        """Test create_integration_with_permissions when integration creation fails."""

        mock_dd_request.return_value = ('{"error": "bad request"}', 400)

        mock_gcloud.return_value = None
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
