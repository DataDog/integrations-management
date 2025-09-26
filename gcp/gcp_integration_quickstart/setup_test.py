import unittest
from unittest.mock import Mock, call, patch

from setup import *


class TestHTTPFunctions(unittest.TestCase):
    """Test the HTTP request functions."""

    @patch(
        "setup.os.environ",
        {
            "DD_API_KEY": "test_api_key",
            "DD_APP_KEY": "test_app_key",
            "DD_SITE": "test.datadog.com",
        },
    )
    @patch("setup.request")
    def test_dd_request_post(self, mock_request):
        """Test dd_request with POST method and body."""
        mock_request.return_value = ("response data", 201)

        result_data, result_status = dd_request(
            "POST", "/test/endpoint", {"test": "data"}
        )

        mock_request.assert_called_once_with(
            "POST",
            "https://api.test.datadog.com/test/endpoint",
            {"test": "data"},
            {
                "Content-Type": "application/json",
                "DD-API-KEY": "test_api_key",
                "DD-APPLICATION-KEY": "test_app_key",
            },
        )
        self.assertEqual(result_data, "response data")
        self.assertEqual(result_status, 201)

    @patch(
        "setup.os.environ",
        {
            "DD_API_KEY": "test_api_key",
            "DD_APP_KEY": "test_app_key",
            "DD_SITE": "test.datadog.com",
        },
    )
    @patch("setup.request")
    def test_dd_request_get(self, mock_request):
        """Test dd_request with GET method."""
        mock_request.return_value = ("response data", 200)

        result_data, result_status = dd_request("GET", "/test/endpoint")

        mock_request.assert_called_once_with(
            "GET",
            "https://api.test.datadog.com/test/endpoint",
            None,
            {
                "Content-Type": "application/json",
                "DD-API-KEY": "test_api_key",
                "DD-APPLICATION-KEY": "test_app_key",
            },
        )
        self.assertEqual(result_data, "response data")
        self.assertEqual(result_status, 200)


class TestIsValidWorkflowId(unittest.TestCase):
    """Test the is_valid_workflow_id function."""

    @patch(
        "setup.os.environ",
        {
            "DD_API_KEY": "test_api_key",
            "DD_APP_KEY": "test_app_key",
            "DD_SITE": "test.datadog.com",
        },
    )
    @patch("setup.dd_request")
    def test_is_valid_workflow_id_404(self, mock_dd_request):
        """Test is_valid_workflow_id when workflow doesn't exist (404)."""
        mock_dd_request.return_value = ('{"error": "not found"}', 404)

        result = is_valid_workflow_id("test-workflow-id")

        self.assertTrue(result)
        mock_dd_request.assert_called_once_with(
            "GET",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup/test-workflow-id",
        )

    @patch("setup.dd_request")
    def test_is_valid_workflow_id_with_failed_steps(self, mock_dd_request):
        """Test is_valid_workflow_id when workflow has failed steps."""
        mock_dd_request.return_value = (
            '{"data": {"attributes": {"statuses": [{"status": "failed"}, {"status": "finished"}]}}}',
            200,
        )

        result = is_valid_workflow_id("test-workflow-id")

        self.assertFalse(result)
        mock_dd_request.assert_called_once_with(
            "GET",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup/test-workflow-id",
        )

    @patch("setup.dd_request")
    def test_is_valid_workflow_id_workflow_completed(self, mock_dd_request):
        """Test is_valid_workflow_id when workflow has completed successfully."""
        mock_dd_request.return_value = (
            '{"data": {"attributes": {"statuses": [{"step": "create_integration_with_permissions", "status": "finished"}]}}}',
            200,
        )

        result = is_valid_workflow_id("test-workflow-id")

        self.assertFalse(result)
        mock_dd_request.assert_called_once_with(
            "GET",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup/test-workflow-id",
        )

    @patch("setup.dd_request")
    def test_is_valid_workflow_id_workflow_in_progress(self, mock_dd_request):
        """Test is_valid_workflow_id when workflow is still in progress."""
        mock_dd_request.return_value = (
            '{"data": {"attributes": {"statuses": [{"step": "scopes", "status": "finished"}, {"step": "selections", "status": "in_progress"}]}}}',
            200,
        )

        result = is_valid_workflow_id("test-workflow-id")

        self.assertTrue(result)
        mock_dd_request.assert_called_once_with(
            "GET",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup/test-workflow-id",
        )

    @patch(
        "setup.os.environ",
        {
            "DD_API_KEY": "test_api_key",
            "DD_APP_KEY": "test_app_key",
            "DD_SITE": "test.datadog.com",
        },
    )
    @patch("setup.dd_request")
    def test_is_valid_workflow_id_api_error(self, mock_dd_request):
        """Test is_valid_workflow_id when API returns error status."""
        mock_dd_request.return_value = ('{"error": "server error"}', 500)

        result = is_valid_workflow_id("test-workflow-id")

        self.assertFalse(result)
        mock_dd_request.assert_called_once_with(
            "GET",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup/test-workflow-id",
        )


class TestWorkflowReporter(unittest.TestCase):
    """Test the WorkflowReporter class."""

    def setUp(self):
        """Set up test fixtures."""
        self.workflow_reporter = WorkflowReporter("test_workflow_id")

    @patch("setup.dd_request")
    def test_report(self, mock_dd_request):
        """Test the report method."""
        metadata = {"key": "value"}
        message = "Test message"

        mock_dd_request.return_value = ('{"status": "ok"}', 201)

        self.workflow_reporter.report(
            "test_step", Status.IN_PROGRESS, metadata=metadata, message=message
        )

        mock_dd_request.assert_called_once_with(
            "POST",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup",
            {
                "data": {
                    "id": "test_workflow_id",
                    "type": "integration_setup_status",
                    "attributes": {
                        "status": Status.IN_PROGRESS.value,
                        "step": "test_step",
                        "metadata": metadata,
                        "message": message,
                    },
                }
            },
        )

    @patch("setup.dd_request")
    def test_report_failure(self, mock_dd_request):
        """Test the report method when API returns non-201."""
        mock_dd_request.return_value = ('{"error": "bad request"}', 400)

        with self.assertRaises(RuntimeError) as ctx:
            self.workflow_reporter.report("test_step", Status.IN_PROGRESS)

        self.assertEqual(
            str(ctx.exception), 'failed to report status: {"error": "bad request"}'
        )

    @patch("setup.dd_request")
    def test_report_step_context_manager_success(self, mock_dd_request):
        """Test the report_step context manager on success."""

        mock_dd_request.return_value = ('{"status": "ok"}', 201)

        with self.workflow_reporter.report_step("test_step") as step_reporter:
            self.assertEqual(step_reporter.step_id, "test_step")

        # Should be called twice: once for IN_PROGRESS, once for FINISHED
        self.assertEqual(mock_dd_request.call_count, 2)

        # Check the IN_PROGRESS call
        mock_dd_request.assert_any_call(
            "POST",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup",
            {
                "data": {
                    "id": "test_workflow_id",
                    "type": "integration_setup_status",
                    "attributes": {
                        "status": Status.IN_PROGRESS.value,
                        "step": "test_step",
                        "metadata": None,
                        "message": None,
                    },
                }
            },
        )

        # Check the FINISHED call
        mock_dd_request.assert_any_call(
            "POST",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup",
            {
                "data": {
                    "id": "test_workflow_id",
                    "type": "integration_setup_status",
                    "attributes": {
                        "status": Status.FINISHED.value,
                        "step": "test_step",
                        "metadata": None,
                        "message": None,
                    },
                }
            },
        )

    @patch("setup.dd_request")
    def test_report_step_context_manager_exception(self, mock_dd_request):
        """Test the report_step context manager on exception."""

        mock_dd_request.return_value = ('{"status": "ok"}', 201)

        with self.assertRaises(ValueError):
            with self.workflow_reporter.report_step("test_step") as step_reporter:
                self.assertEqual(step_reporter.step_id, "test_step")
                raise ValueError("Test exception")

        self.assertEqual(mock_dd_request.call_count, 2)

        mock_dd_request.assert_any_call(
            "POST",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup",
            {
                "data": {
                    "id": "test_workflow_id",
                    "type": "integration_setup_status",
                    "attributes": {
                        "status": Status.IN_PROGRESS.value,
                        "step": "test_step",
                        "metadata": None,
                        "message": None,
                    },
                }
            },
        )

        mock_dd_request.assert_any_call(
            "POST",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup",
            {
                "data": {
                    "id": "test_workflow_id",
                    "type": "integration_setup_status",
                    "attributes": {
                        "status": Status.FAILED.value,
                        "step": "test_step",
                        "metadata": None,
                        "message": "Test exception",
                    },
                }
            },
        )


class TestGCloudFunction(unittest.TestCase):
    """Test the gcloud function and related gcloud operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.workflow_reporter = WorkflowReporter("test_workflow_id")

    @patch("setup.subprocess.run")
    def test_gcloud_success(self, mock_run):
        """Test successful gcloud command execution."""
        mock_result = Mock()
        mock_result.stdout = '{"test": "data"}'
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        result = gcloud("projects list")

        mock_run.assert_called_once_with(
            "gcloud projects list --format=json",
            shell=True,
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result, {"test": "data"})

    @patch("setup.subprocess.run")
    def test_gcloud_with_keys(self, mock_run):
        """Test gcloud command with specific keys."""
        mock_result = Mock()
        mock_result.stdout = '{"test": "data"}'
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        result = gcloud("projects list", "name", "projectId")

        mock_run.assert_called_once_with(
            'gcloud projects list --format="json(name,projectId)"',
            shell=True,
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result, {"test": "data"})

    @patch("setup.subprocess.run")
    def test_gcloud_failure(self, mock_run):
        """Test gcloud command failure."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "gcloud", stderr="Error message"
        )

        with self.assertRaises(RuntimeError) as context:
            gcloud("invalid command")

        self.assertIn("could not execute gcloud command", str(context.exception))

    @patch("setup.gcloud")
    def test_ensure_login_success(self, mock_gcloud):
        """Test ensure_login when user is logged in."""
        mock_gcloud.return_value = [{"token": "dummy-token"}]

        # Should not raise an exception
        ensure_login()

        mock_gcloud.assert_called_once_with("auth print-access-token")

    @patch("setup.gcloud")
    def test_ensure_login_failure(self, mock_gcloud):
        """Test ensure_login when user is not logged in."""
        mock_gcloud.return_value = []

        with self.assertRaises(RuntimeError) as context:
            ensure_login()

        self.assertIn("not logged in to GCloud Shell", str(context.exception))

    @patch("setup.gcloud")
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

    @patch("setup.gcloud")
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

    @patch("setup.gcloud")
    @patch("setup.dd_request")
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

    @patch("setup.dd_request")
    def test_assign_delegate_permissions_sts_failure(self, mock_dd_request):
        """Test assign_delegate_permissions when STS delegate request fails."""

        # Mock dd_request response for STS delegate failure
        mock_dd_request.return_value = ('{"error": "not found"}', 404)

        # Create a mock step reporter
        step_reporter = Mock()

        with self.assertRaises(RuntimeError) as context:
            assign_delegate_permissions(step_reporter, "test-project")

        self.assertIn("failed to get sts delegate", str(context.exception))

    @patch("setup.gcloud")
    @patch("setup.dd_request")
    @patch("setup.request")
    def test_collect_configuration_scopes_get_service_accounts_404(
        self, mock_request, mock_dd_request, mock_gcloud
    ):
        """Test collect_configuration_scopes when get service accounts endpoint returns 404 (no existing accounts)."""

        # Mock dd_request response for 404 (no existing accounts)
        mock_dd_request.return_value = ('{"error": "not found"}', 404)

        # Mock request responses for IAM permissions checks
        mock_request.return_value = (
            '{"permissions": ["resourcemanager.projects.setIamPolicy", "serviceusage.services.enable"]}',
            200,
        )

        # Mock gcloud responses for auth token, projects, and folders
        def gcloud_side_effect(cmd, *_):
            if "auth print-access-token" in cmd:
                return {"token": "test-token"}
            elif "projects list" in cmd:
                return [
                    {
                        "name": "Test Project",
                        "projectId": "test-project",
                        "parent": {"id": "parent123"},
                    }
                ]
            elif "alpha resource-manager folders search" in cmd:
                return [
                    {
                        "displayName": "Test Folder",
                        "name": "folders/folder123",
                        "parent": "folders/parent456",
                    }
                ]
            else:
                return None

        mock_gcloud.side_effect = gcloud_side_effect

        step_reporter = Mock()

        # Should not raise an exception
        collect_configuration_scopes(step_reporter)

        # Verify dd_request was called
        mock_dd_request.assert_called_once_with(
            "GET", "/api/v2/integration/gcp/accounts"
        )

        # Verify gcloud was called for auth token, projects and folders
        expected_gcloud_calls = [
            call(
                'projects list         --filter="lifecycleState=ACTIVE AND NOT projectId:sys*"',
                "name",
                "projectId",
                "parent.id",
            ),
            call(
                'alpha resource-manager folders search         --query="lifecycleState=ACTIVE"',
                "displayName",
                "name",
                "parent",
            ),
            call("auth print-access-token"),
        ]
        mock_gcloud.assert_has_calls(expected_gcloud_calls)

        # Verify step_reporter.report was called with metadata
        step_reporter.report.assert_called_once()
        call_args = step_reporter.report.call_args
        self.assertIn("metadata", call_args.kwargs)
        metadata = call_args.kwargs["metadata"]
        self.assertIn("folders", metadata)
        self.assertIn("projects", metadata)

    @patch("setup.gcloud")
    @patch("setup.dd_request")
    @patch("setup.request")
    def test_collect_configuration_scopes_get_service_accounts_200(
        self, mock_request, mock_dd_request, mock_gcloud
    ):
        """Test collect_configuration_scopes when get service accounts endpoint returns 200 (existing accounts)."""

        # Mock dd_request response for 200 (existing accounts)
        mock_dd_request.return_value = (
            '{"data": [{"meta": {"accessible_projects": ["existing-project"]}}]}',
            200,
        )

        # Mock request responses for IAM permissions checks
        mock_request.return_value = (
            '{"permissions": ["resourcemanager.projects.setIamPolicy", "serviceusage.services.enable"]}',
            200,
        )

        # Mock gcloud responses for auth token, projects, and folders
        def gcloud_side_effect(cmd, *_):
            if "auth print-access-token" in cmd:
                return {"token": "test-token"}
            elif "projects list" in cmd:
                return [
                    {
                        "name": "Test Project",
                        "projectId": "test-project",
                        "parent": {"id": "parent123"},
                    }
                ]
            elif "alpha resource-manager folders search" in cmd:
                return [
                    {
                        "displayName": "Test Folder",
                        "name": "folders/folder123",
                        "parent": "folders/parent456",
                    }
                ]
            else:
                return None

        mock_gcloud.side_effect = gcloud_side_effect

        step_reporter = Mock()

        collect_configuration_scopes(step_reporter)

        # Verify dd_request was called
        mock_dd_request.assert_called_once_with(
            "GET", "/api/v2/integration/gcp/accounts"
        )

        # Verify gcloud was called for auth token, projects and folders
        expected_gcloud_calls = [
            call(
                'projects list         --filter="lifecycleState=ACTIVE AND NOT projectId:sys*"',
                "name",
                "projectId",
                "parent.id",
            ),
            call(
                'alpha resource-manager folders search         --query="lifecycleState=ACTIVE"',
                "displayName",
                "name",
                "parent",
            ),
            call("auth print-access-token"),
        ]
        mock_gcloud.assert_has_calls(expected_gcloud_calls)

        # Verify step_reporter.report was called with metadata
        step_reporter.report.assert_called_once()
        call_args = step_reporter.report.call_args
        self.assertIn("metadata", call_args.kwargs)
        metadata = call_args.kwargs["metadata"]
        self.assertIn("folders", metadata)
        self.assertIn("projects", metadata)

    @patch("setup.dd_request")
    def test_collect_configuration_scopes_get_service_accounts_error(
        self, mock_dd_request
    ):
        """Test collect_configuration_scopes when get service accounts endpoint returns an error status."""

        # Mock dd_request response for error (500)
        mock_dd_request.return_value = ('{"error": "server error"}', 500)

        step_reporter = Mock()

        # Should raise an exception
        with self.assertRaises(RuntimeError) as context:
            collect_configuration_scopes(step_reporter)

        self.assertIn("failed to get service accounts", str(context.exception))

        # Verify dd_request was called
        mock_dd_request.assert_called_once_with(
            "GET", "/api/v2/integration/gcp/accounts"
        )


class TestFetchIamPermissionsFor(unittest.TestCase):
    """Test the fetch_iam_permissions_for function."""

    @patch("setup.request")
    def test_fetch_iam_permissions_for_project(self, mock_request):
        """Test fetch_iam_permissions_for for a project."""
        mock_request.return_value = ('{"permissions": ["test"]}', 200)

        project = Project(
            parent_id="parent123",
            id="project123",
            name="Test Project",
            is_already_monitored=False,
        )

        result_scope, result_response, result_status = fetch_iam_permissions_for(
            project, "test_token"
        )

        mock_request.assert_called_once_with(
            "POST",
            "https://cloudresourcemanager.googleapis.com/v1/projects/project123:testIamPermissions",
            {"permissions": project.required_permissions},
            {
                "Authorization": "Bearer test_token",
                "Content-Type": "application/json",
            },
        )
        self.assertEqual(result_scope, project)
        self.assertEqual(result_response, '{"permissions": ["test"]}')
        self.assertEqual(result_status, 200)

    @patch("setup.request")
    def test_fetch_iam_permissions_for_folder(self, mock_request):
        """Test fetch_iam_permissions_for for a folder."""
        mock_request.return_value = ('{"permissions": ["test"]}', 200)

        folder = Folder(parent_id="parent123", id="folder123", name="Test Folder")

        result_scope, result_response, result_status = fetch_iam_permissions_for(
            folder, "test_token"
        )

        mock_request.assert_called_once_with(
            "POST",
            "https://cloudresourcemanager.googleapis.com/v2/folders/folder123:testIamPermissions",
            {"permissions": folder.required_permissions},
            {
                "Authorization": "Bearer test_token",
                "Content-Type": "application/json",
            },
        )
        self.assertEqual(result_scope, folder)
        self.assertEqual(result_response, '{"permissions": ["test"]}')
        self.assertEqual(result_status, 200)


class TestCreateIntegrationWithPermissions(unittest.TestCase):
    """Test the create_integration_with_permissions method."""

    def setUp(self):
        """Set up test fixtures."""
        self.workflow_reporter = WorkflowReporter("test_workflow_id")
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

    @patch("setup.gcloud")
    @patch("setup.dd_request")
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

    @patch("setup.gcloud")
    @patch("setup.dd_request")
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


class TestIsScopesStepAlreadyCompleted(unittest.TestCase):
    """Test the is_scopes_step_already_completed function."""

    @patch(
        "setup.os.environ",
        {
            "DD_API_KEY": "test_api_key",
            "DD_APP_KEY": "test_app_key",
            "DD_SITE": "test.datadog.com",
        },
    )
    @patch("setup.dd_request")
    def test_is_scopes_step_already_completed_success(self, mock_dd_request):
        """Test is_scopes_step_already_completed when scopes step is finished."""
        mock_dd_request.return_value = (
            '{"data": {"attributes": {"statuses": [{"step": "scopes", "status": "finished"}]}}}',
            200,
        )

        result = is_scopes_step_already_completed("test-workflow-id")

        self.assertTrue(result)
        mock_dd_request.assert_called_once_with(
            "GET",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup/test-workflow-id",
        )

    @patch(
        "setup.os.environ",
        {
            "DD_API_KEY": "test_api_key",
            "DD_APP_KEY": "test_app_key",
            "DD_SITE": "test.datadog.com",
        },
    )
    @patch("setup.dd_request")
    def test_is_scopes_step_already_completed_not_finished(self, mock_dd_request):
        """Test is_scopes_step_already_completed when scopes step is not finished."""
        mock_dd_request.return_value = (
            '{"data": {"attributes": {"statuses": [{"step": "scopes", "status": "in_progress"}]}}}',
            200,
        )

        result = is_scopes_step_already_completed("test-workflow-id")

        self.assertFalse(result)
        mock_dd_request.assert_called_once_with(
            "GET",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup/test-workflow-id",
        )

    @patch(
        "setup.os.environ",
        {
            "DD_API_KEY": "test_api_key",
            "DD_APP_KEY": "test_app_key",
            "DD_SITE": "test.datadog.com",
        },
    )
    @patch("setup.dd_request")
    def test_is_scopes_step_already_completed_no_scopes_step(self, mock_dd_request):
        """Test is_scopes_step_already_completed when no scopes step exists."""
        mock_dd_request.return_value = (
            '{"data": {"attributes": {"statuses": [{"step": "other_step", "status": "finished"}]}}}',
            200,
        )

        result = is_scopes_step_already_completed("test-workflow-id")

        self.assertFalse(result)
        mock_dd_request.assert_called_once_with(
            "GET",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup/test-workflow-id",
        )

    @patch(
        "setup.os.environ",
        {
            "DD_API_KEY": "test_api_key",
            "DD_APP_KEY": "test_app_key",
            "DD_SITE": "test.datadog.com",
        },
    )
    @patch("setup.dd_request")
    def test_is_scopes_step_already_completed_http_error(self, mock_dd_request):
        """Test is_scopes_step_already_completed when HTTP request fails."""
        mock_dd_request.return_value = ('{"error": "not found"}', 404)

        result = is_scopes_step_already_completed("test-workflow-id")

        self.assertFalse(result)
        mock_dd_request.assert_called_once_with(
            "GET",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup/test-workflow-id",
        )


if __name__ == "__main__":
    unittest.main()
