# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import unittest
from unittest.mock import patch

from gcp_integration_quickstart.workflow import (
    ensure_login,
    is_scopes_step_already_completed,
    is_valid_workflow_id,
)


class TestIsValidWorkflowId(unittest.TestCase):
    """Test the is_valid_workflow_id function."""

    @patch("gcp_integration_quickstart.workflow.dd_request")
    def test_is_valid_workflow_id_404(self, mock_dd_request):
        """Test is_valid_workflow_id when workflow doesn't exist (404)."""
        mock_dd_request.return_value = ('{"error": "not found"}', 404)

        result = is_valid_workflow_id("test-workflow-id")

        self.assertTrue(result)
        mock_dd_request.assert_called_once_with(
            "GET",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup/test-workflow-id",
        )

    @patch("gcp_integration_quickstart.workflow.dd_request")
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

    @patch("gcp_integration_quickstart.workflow.dd_request")
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

    @patch("gcp_integration_quickstart.workflow.dd_request")
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

    @patch("gcp_integration_quickstart.workflow.dd_request")
    def test_is_valid_workflow_id_api_error(self, mock_dd_request):
        """Test is_valid_workflow_id when API returns error status."""
        mock_dd_request.return_value = ('{"error": "server error"}', 500)

        result = is_valid_workflow_id("test-workflow-id")

        self.assertFalse(result)
        mock_dd_request.assert_called_once_with(
            "GET",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup/test-workflow-id",
        )


class TestEnsureLogin(unittest.TestCase):
    """Test the ensure_login function."""

    @patch("gcp_integration_quickstart.workflow.gcloud")
    def test_ensure_login_success(self, mock_gcloud):
        """Test ensure_login when user is logged in."""
        mock_gcloud.return_value = [{"token": "dummy-token"}]

        # Should not raise an exception
        ensure_login()

        mock_gcloud.assert_called_once_with("auth print-access-token")

    @patch("gcp_integration_quickstart.workflow.gcloud")
    def test_ensure_login_failure(self, mock_gcloud):
        """Test ensure_login when user is not logged in."""
        mock_gcloud.return_value = []

        with self.assertRaises(RuntimeError) as context:
            ensure_login()

        self.assertIn("not logged in to GCloud Shell", str(context.exception))


class TestIsScopesStepAlreadyCompleted(unittest.TestCase):
    """Test the is_scopes_step_already_completed function."""

    @patch("gcp_integration_quickstart.workflow.dd_request")
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

    @patch("gcp_integration_quickstart.workflow.dd_request")
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

    @patch("gcp_integration_quickstart.workflow.dd_request")
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

    @patch("gcp_integration_quickstart.workflow.dd_request")
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
