# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import json
import unittest
from unittest.mock import Mock, patch
import os
from contextlib import contextmanager

from gcp_integration_quickstart.integration_configuration import (
    REQUIRED_APIS,
    REQUIRED_ROLES,
    CUSTOM_ORG_ROLE_ID,
    CUSTOM_ORG_ROLE_PERMISSIONS,
    assign_delegate_permissions,
    assign_organization_permissions,
    create_integration_with_permissions,
    create_logs_forwarding_integration,
)

from gcp_integration_quickstart.models import (
    IntegrationConfiguration,
    ProductRequirements,
    LogsForwardingConfiguration,
)

from gcp_shared.dataflow_models import DataflowConfiguration, ExclusionFilter
from gcp_shared.gcloud import GcloudCmd
from gcp_shared.models import (
    ConfigurationScope,
    Folder,
    Project,
)
from gcp_shared.service_accounts import find_or_create_service_account
from gcp_integration_quickstart.main import main


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
            "iam service-accounts list --project test-project '--filter=email='\"'\"'test-account@test-project.iam.gserviceaccount.com'\"'\"''",
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
            "iam service-accounts list --project test-project '--filter=email='\"'\"'test-account@test-project.iam.gserviceaccount.com'\"'\"''",
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


class TestAssignOrganizationPermissions(unittest.TestCase):
    """Test the assign_organization_permissions function."""

    @patch("gcp_integration_quickstart.integration_configuration.gcloud")
    def test_assign_organization_permissions_creates_new_role(self, mock_gcloud):
        """Test assign_organization_permissions when the custom role does not exist yet."""

        mock_gcloud.side_effect = [
            [
                {"id": "test-project", "type": "project"},
                {"id": "org-123", "type": "organization"},
            ],
            [],
            None,
            None,
        ]

        step_reporter = Mock()

        assign_organization_permissions(
            step_reporter,
            "test-sa@test-project.iam.gserviceaccount.com",
            "test-project",
        )

        actual_commands = [str(call[0][0]) for call in mock_gcloud.call_args_list]

        self.assertEqual(len(actual_commands), 4)
        self.assertEqual(
            actual_commands[0],
            str(GcloudCmd("projects", "get-ancestors").arg("test-project")),
        )
        self.assertEqual(
            actual_commands[1],
            str(
                GcloudCmd("iam roles", "list")
                .param("--organization", "org-123")
                .param_equals(
                    "--filter",
                    f"name='organizations/org-123/roles/{CUSTOM_ORG_ROLE_ID}'",
                )
            ),
        )
        self.assertEqual(
            actual_commands[2],
            str(
                GcloudCmd("iam roles", "create")
                .arg(CUSTOM_ORG_ROLE_ID)
                .param("--organization", "org-123")
                .param("--title", "Datadog Org Folder Resource Collection Role")
                .param(
                    "--description",
                    "Grants Datadog necessary permissions to collect org/folder resources via Cloud Asset Inventory",
                )
                .param(
                    "--permissions",
                    ",".join(CUSTOM_ORG_ROLE_PERMISSIONS),
                )
                .param("--stage", "GA")
                .flag("--quiet")
            ),
        )
        self.assertEqual(
            actual_commands[3],
            str(
                GcloudCmd("organizations", "add-iam-policy-binding")
                .arg("org-123")
                .param(
                    "--member",
                    "serviceAccount:test-sa@test-project.iam.gserviceaccount.com",
                )
                .param("--role", f"organizations/org-123/roles/{CUSTOM_ORG_ROLE_ID}")
                .param("--condition", "None")
                .flag("--quiet")
            ),
        )

    @patch("gcp_integration_quickstart.integration_configuration.gcloud")
    def test_assign_organization_permissions_updates_existing_role(self, mock_gcloud):
        """Test assign_organization_permissions when the custom role already exists."""

        mock_gcloud.side_effect = [
            [{"id": "org-123", "type": "organization"}],
            [{"name": f"organizations/org-123/roles/{CUSTOM_ORG_ROLE_ID}"}],
            None,
            None,
        ]

        step_reporter = Mock()

        assign_organization_permissions(
            step_reporter,
            "test-sa@test-project.iam.gserviceaccount.com",
            "test-project",
        )

        actual_commands = [str(call[0][0]) for call in mock_gcloud.call_args_list]

        self.assertEqual(len(actual_commands), 4)
        self.assertTrue(actual_commands[2].startswith("iam roles update"))

    @patch("gcp_integration_quickstart.integration_configuration.gcloud")
    def test_assign_organization_permissions_no_org_found(self, mock_gcloud):
        """Test assign_organization_permissions when no organization ancestor can be found."""

        mock_gcloud.return_value = [{"id": "test-project", "type": "project"}]

        step_reporter = Mock()

        with self.assertRaises(RuntimeError) as context:
            assign_organization_permissions(
                step_reporter,
                "test-sa@test-project.iam.gserviceaccount.com",
                "test-project",
            )

        self.assertIn("could not determine organization_id", str(context.exception))


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
            is_org_folder_resource_collection_enabled=False,
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
                        "is_org_folder_resource_collection_enabled": False,
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

@contextmanager
def _step_ctx(step_reporter):
    yield step_reporter


class TestMainLogsForwardingConfiguration(unittest.TestCase):
    def setUp(self):
        self.env = {
            "DD_API_KEY": "x",
            "DD_APP_KEY": "y",
            "DD_SITE": "datad0g.com",
            "WORKFLOW_ID": "11111111-1111-1111-1111-111111111111",
        }

    @patch("gcp_integration_quickstart.main.signal.signal")
    @patch("gcp_integration_quickstart.main.create_logs_forwarding_integration")
    @patch("gcp_integration_quickstart.main.create_integration_with_permissions")
    @patch("gcp_integration_quickstart.main.assign_organization_permissions")
    @patch("gcp_integration_quickstart.main.assign_delegate_permissions")
    @patch("gcp_integration_quickstart.main.find_or_create_service_account")
    @patch("gcp_integration_quickstart.main.WorkflowReporter")
    def test_main_calls_create_logs_forwarding_when_present(
        self,
        mock_workflow_reporter_cls,
        mock_find_or_create_sa,
        _mock_assign_delegate,
        mock_assign_organization_permissions,
        mock_create_integration,
        mock_create_logs_forwarding,
        _mock_signal,
    ):
        user_selections = {
            "service_account_id": "my-sa",
            "default_project_id": "my-project",
            "projects": [],
            "folders": [],
            "integration_configuration": {
                "metric_namespace_configs": [{"namespace": "test"}],
                "monitored_resource_configs": [{"cloud_run": ["filter1"]}],
                "account_tags": ["tag1"],
                "resource_collection_enabled": True,
                "automute": False,
                "region_filter_configs": [],
                "is_global_location_enabled": True,
            },
            "logs_forwarding_configuration": {
                "region": "us-central1",
                "inclusion_filter": "",
                "exclusion_filters": [
                    {"filter": "resource.type=gce_instance", "name": "ex1"}
                ],
                "dataflow_configuration": {
                    "is_dataflow_prime_enabled": False,
                    "is_streaming_engine_enabled": False,
                    "max_workers": 5,
                    "num_workers": 1,
                    "machine_type": "n1-standard-1",
                    "parallelism": 1,
                    "batch_size": 100,
                },
            },
        }

        step_reporter = Mock()

        workflow_reporter = Mock()
        workflow_reporter.is_valid_workflow_id.return_value = True
        workflow_reporter.is_scopes_step_already_completed.return_value = True
        workflow_reporter.receive_user_selections.return_value = user_selections
        workflow_reporter.report_step.side_effect = lambda *_a, **_k: _step_ctx(
            step_reporter
        )

        mock_workflow_reporter_cls.return_value = workflow_reporter
        mock_find_or_create_sa.return_value = "sa@my-project.iam.gserviceaccount.com"

        with patch.dict(os.environ, self.env, clear=True):
            main()

        mock_create_integration.assert_called_once()
        mock_create_logs_forwarding.assert_called_once()
        mock_assign_organization_permissions.assert_not_called()

    @patch("gcp_integration_quickstart.main.signal.signal")
    @patch("gcp_integration_quickstart.main.create_logs_forwarding_integration")
    @patch("gcp_integration_quickstart.main.create_integration_with_permissions")
    @patch("gcp_integration_quickstart.main.assign_organization_permissions")
    @patch("gcp_integration_quickstart.main.assign_delegate_permissions")
    @patch("gcp_integration_quickstart.main.find_or_create_service_account")
    @patch("gcp_integration_quickstart.main.WorkflowReporter")
    def test_main_skips_create_logs_forwarding_when_missing(
        self,
        mock_workflow_reporter_cls,
        mock_find_or_create_sa,
        _mock_assign_delegate,
        mock_assign_organization_permissions,
        mock_create_integration,
        mock_create_logs_forwarding,
        _mock_signal,
    ):
        user_selections = {
            "service_account_id": "my-sa",
            "default_project_id": "my-project",
            "projects": [],
            "folders": [],
            "integration_configuration": {
                "metric_namespace_configs": [{"namespace": "test"}],
                "monitored_resource_configs": [{"cloud_run": ["filter1"]}],
                "account_tags": ["tag1"],
                "resource_collection_enabled": True,
                "automute": False,
                "region_filter_configs": [],
                "is_global_location_enabled": True,
            },
        }

        step_reporter = Mock()

        workflow_reporter = Mock()
        workflow_reporter.is_valid_workflow_id.return_value = True
        workflow_reporter.is_scopes_step_already_completed.return_value = True
        workflow_reporter.receive_user_selections.return_value = user_selections
        workflow_reporter.report_step.side_effect = lambda *_a, **_k: _step_ctx(
            step_reporter
        )

        mock_workflow_reporter_cls.return_value = workflow_reporter
        mock_find_or_create_sa.return_value = "sa@my-project.iam.gserviceaccount.com"

        with patch.dict(os.environ, self.env, clear=True):
            main()

        mock_create_integration.assert_called_once()
        mock_create_logs_forwarding.assert_not_called()
        mock_assign_organization_permissions.assert_not_called()

    @patch("gcp_integration_quickstart.main.signal.signal")
    @patch("gcp_integration_quickstart.main.create_logs_forwarding_integration")
    @patch("gcp_integration_quickstart.main.create_integration_with_permissions")
    @patch("gcp_integration_quickstart.main.assign_organization_permissions")
    @patch("gcp_integration_quickstart.main.assign_delegate_permissions")
    @patch("gcp_integration_quickstart.main.find_or_create_service_account")
    @patch("gcp_integration_quickstart.main.WorkflowReporter")
    def test_main_assigns_organization_permissions_when_enabled(
        self,
        mock_workflow_reporter_cls,
        mock_find_or_create_sa,
        _mock_assign_delegate,
        mock_assign_organization_permissions,
        mock_create_integration,
        mock_create_logs_forwarding,
        _mock_signal,
    ):
        user_selections = {
            "service_account_id": "my-sa",
            "default_project_id": "my-project",
            "projects": [],
            "folders": [],
            "integration_configuration": {
                "metric_namespace_configs": [{"namespace": "test"}],
                "monitored_resource_configs": [{"cloud_run": ["filter1"]}],
                "account_tags": ["tag1"],
                "resource_collection_enabled": True,
                "automute": False,
                "region_filter_configs": [],
                "is_global_location_enabled": True,
                "is_org_folder_resource_collection_enabled": True,
            },
        }

        step_reporter = Mock()

        workflow_reporter = Mock()
        workflow_reporter.is_valid_workflow_id.return_value = True
        workflow_reporter.is_scopes_step_already_completed.return_value = True
        workflow_reporter.receive_user_selections.return_value = user_selections
        workflow_reporter.report_step.side_effect = lambda *_a, **_k: _step_ctx(
            step_reporter
        )

        mock_workflow_reporter_cls.return_value = workflow_reporter
        mock_find_or_create_sa.return_value = "sa@my-project.iam.gserviceaccount.com"

        with patch.dict(os.environ, self.env, clear=True):
            main()

        mock_assign_organization_permissions.assert_called_once_with(
            step_reporter,
            "sa@my-project.iam.gserviceaccount.com",
            "my-project",
        )
        mock_create_integration.assert_called_once()
        mock_create_logs_forwarding.assert_not_called()

    @patch("gcp_integration_quickstart.integration_configuration.create_dataflow_job")
    @patch(
        "gcp_integration_quickstart.integration_configuration.assign_required_dataflow_roles"
    )
    @patch("gcp_integration_quickstart.integration_configuration.create_log_sinks")
    @patch(
        "gcp_integration_quickstart.integration_configuration.create_secret_manager_entry"
    )
    @patch(
        "gcp_integration_quickstart.integration_configuration.create_dataflow_staging_bucket"
    )
    @patch(
        "gcp_integration_quickstart.integration_configuration.create_topics_with_subscription"
    )
    def test_create_logs_forwarding_integration_success_when_called(
        self,
        mock_create_topics,
        mock_create_bucket,
        mock_create_secret,
        mock_create_log_sinks,
        mock_assign_roles,
        mock_create_job,
    ):
        step_reporter = Mock()
        service_account_email = "test-sa@test-project.iam.gserviceaccount.com"
        default_project_id = "default-project"
        configuration_scope = ConfigurationScope(projects=[], folders=[])

        logs_cfg = LogsForwardingConfiguration(
            region="us-central1",
            inclusion_filter="severity>=ERROR",
            exclusion_filters=[
                {"filter": "resource.type=gce_instance", "name": "ex1"},
            ],
            dataflow_configuration={
                "is_dataflow_prime_enabled": False,
                "is_streaming_engine_enabled": False,
                "max_workers": 7,
                "num_workers": 2,
                "machine_type": "n1-standard-1",
                "parallelism": 3,
                "batch_size": 111,
            },
        )

        create_logs_forwarding_integration(
            step_reporter,
            service_account_email,
            logs_cfg,
            default_project_id,
            configuration_scope,
        )

        mock_create_topics.assert_called_once_with(
            step_reporter, default_project_id, service_account_email
        )
        mock_create_bucket.assert_called_once_with(
            step_reporter, default_project_id, service_account_email, logs_cfg.region
        )
        mock_create_secret.assert_called_once_with(
            step_reporter, default_project_id, service_account_email
        )
        mock_create_log_sinks.assert_called_once_with(
            step_reporter,
            default_project_id,
            configuration_scope,
            logs_cfg.inclusion_filter,
            exclusion_filters=[
                ExclusionFilter(filter="resource.type=gce_instance", name="ex1")
            ],
        )
        mock_assign_roles.assert_called_once_with(
            step_reporter, service_account_email, default_project_id
        )

        df_args = mock_create_job.call_args.args
        self.assertEqual(
            df_args[:4],
            (step_reporter, default_project_id, service_account_email, logs_cfg.region),
        )
        self.assertIsInstance(df_args[4], DataflowConfiguration)
        self.assertEqual(df_args[4].max_workers, 7)
        self.assertEqual(df_args[4].batch_size, 111)

class TestMainExistingServiceAccount(unittest.TestCase):
    def setUp(self):
        self.env = {
            "DD_API_KEY": "x",
            "DD_APP_KEY": "y",
            "DD_SITE": "datad0g.com",
            "WORKFLOW_ID": "11111111-1111-1111-1111-111111111111",
        }
        self.base_selections = {
            "default_project_id": "my-project",
            "projects": [],
            "folders": [],
            "integration_configuration": {
                "metric_namespace_configs": [],
                "monitored_resource_configs": [],
                "account_tags": [],
                "resource_collection_enabled": True,
                "automute": False,
                "region_filter_configs": [],
                "is_global_location_enabled": True,
            },
        }

    def _make_workflow_reporter(self, mock_cls, user_selections):
        step_reporter = Mock()
        workflow_reporter = Mock()
        workflow_reporter.is_valid_workflow_id.return_value = True
        workflow_reporter.is_scopes_step_already_completed.return_value = True
        workflow_reporter.receive_user_selections.return_value = user_selections
        workflow_reporter.report_step.side_effect = lambda *_a, **_k: _step_ctx(step_reporter)
        mock_cls.return_value = workflow_reporter
        return step_reporter

    @patch("gcp_integration_quickstart.main.signal.signal")
    @patch("gcp_integration_quickstart.main.create_integration_with_permissions")
    @patch("gcp_integration_quickstart.main.assign_delegate_permissions")
    @patch("gcp_integration_quickstart.main.validate_service_account_in_project")
    @patch("gcp_integration_quickstart.main.find_or_create_service_account")
    @patch("gcp_integration_quickstart.main.WorkflowReporter")
    def test_main_uses_existing_sa_when_provided(
        self,
        mock_workflow_reporter_cls,
        mock_find_or_create,
        mock_validate,
        _mock_assign,
        _mock_create_integration,
        _mock_signal,
    ):
        selections = {
            **self.base_selections,
            "existing_service_account_email": "existing@my-project.iam.gserviceaccount.com",
        }
        self._make_workflow_reporter(mock_workflow_reporter_cls, selections)

        with patch.dict(os.environ, self.env, clear=True):
            main()

        mock_find_or_create.assert_not_called()
        mock_validate.assert_called_once_with(
            mock_validate.call_args[0][0],
            "existing@my-project.iam.gserviceaccount.com",
            "my-project",
        )

    @patch("gcp_integration_quickstart.main.signal.signal")
    @patch("gcp_integration_quickstart.main.create_integration_with_permissions")
    @patch("gcp_integration_quickstart.main.assign_delegate_permissions")
    @patch("gcp_integration_quickstart.main.find_or_create_service_account")
    @patch("gcp_integration_quickstart.main.WorkflowReporter")
    def test_main_falls_back_to_create_when_no_existing_sa(
        self,
        mock_workflow_reporter_cls,
        mock_find_or_create,
        _mock_assign,
        _mock_create_integration,
        _mock_signal,
    ):
        selections = {**self.base_selections, "service_account_id": "my-sa"}
        self._make_workflow_reporter(mock_workflow_reporter_cls, selections)
        mock_find_or_create.return_value = "my-sa@my-project.iam.gserviceaccount.com"

        with patch.dict(os.environ, self.env, clear=True):
            main()

        mock_find_or_create.assert_called_once()

    @patch("gcp_integration_quickstart.main.signal.signal")
    @patch("gcp_integration_quickstart.main.WorkflowReporter")
    def test_main_rejects_invalid_existing_sa_email(
        self, mock_workflow_reporter_cls, _mock_signal
    ):
        selections = {**self.base_selections, "existing_service_account_email": "not-a-valid-email"}
        self._make_workflow_reporter(mock_workflow_reporter_cls, selections)

        with patch.dict(os.environ, self.env, clear=True):
            with self.assertRaises(ValueError) as ctx:
                main()

        self.assertIn("Invalid service account email", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
