# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import unittest
from unittest.mock import patch

from gcp_shared.reporter import Status, WorkflowReporter


class TestWorkflowReporter(unittest.TestCase):
    """Test the WorkflowReporter class."""

    def setUp(self):
        self.workflow_reporter = WorkflowReporter(
            "test_workflow_id", "gcp-integration-setup"
        )

    @patch("gcp_shared.reporter.dd_request")
    def test_report(self, mock_dd_request):
        metadata = {"key": "value"}
        message = "Test message"
        mock_dd_request.return_value = ('{"status": "ok"}', 201)

        workflow_reporter = WorkflowReporter(
            "test_workflow_id", "gcp-integration-setup"
        )

        # Should not raise an exception
        workflow_reporter.report(
            "test_step", Status.IN_PROGRESS, metadata=metadata, message=message
        )

    @patch("gcp_shared.reporter.dd_request")
    def test_report_failure(self, mock_dd_request):
        mock_dd_request.return_value = ('{"error": "bad request"}', 400)

        workflow_reporter = WorkflowReporter(
            "test_workflow_id", "gcp-integration-setup"
        )

        with self.assertRaises(RuntimeError) as ctx:
            workflow_reporter.report("test_step", Status.IN_PROGRESS)

        self.assertEqual(
            str(ctx.exception), 'failed to report status: {"error": "bad request"}'
        )

    @patch("gcp_shared.reporter.dd_request")
    def test_report_step_context_manager_success(self, mock_dd_request):
        """Test the report_step context manager on success."""
        call_count = 0
        calls = []

        def side_effect(method, path, body):
            nonlocal call_count
            call_count += 1
            calls.append((method, path, body))
            return ('{"status": "ok"}', 201)

        mock_dd_request.side_effect = side_effect

        workflow_reporter = WorkflowReporter(
            "test_workflow_id", "gcp-integration-setup"
        )

        with workflow_reporter.report_step("test_step") as step_reporter:
            self.assertEqual(step_reporter.step_id, "test_step")

        # Should be called twice: once for IN_PROGRESS, once for FINISHED
        self.assertEqual(call_count, 2)

        # Check the IN_PROGRESS call
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(
            calls[0][1],
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup",
        )
        self.assertEqual(
            calls[0][2]["data"]["attributes"]["status"], Status.IN_PROGRESS.value
        )

        # Check the FINISHED call
        self.assertEqual(calls[1][0], "POST")
        self.assertEqual(
            calls[1][1],
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup",
        )
        self.assertEqual(
            calls[1][2]["data"]["attributes"]["status"], Status.FINISHED.value
        )

    @patch("gcp_shared.reporter.dd_request")
    def test_report_step_context_manager_exception(self, mock_dd_request):
        """Test the report_step context manager on exception."""
        call_count = 0
        calls = []

        def side_effect(method, path, body):
            nonlocal call_count
            call_count += 1
            calls.append((method, path, body))
            return ('{"status": "ok"}', 201)

        mock_dd_request.side_effect = side_effect

        workflow_reporter = WorkflowReporter(
            "test_workflow_id", "gcp-integration-setup"
        )

        with self.assertRaises(ValueError):
            with workflow_reporter.report_step("test_step") as step_reporter:
                self.assertEqual(step_reporter.step_id, "test_step")
                raise ValueError("Test exception")

        self.assertEqual(call_count, 2)

        # Check the IN_PROGRESS call
        self.assertEqual(
            calls[0][2]["data"]["attributes"]["status"], Status.IN_PROGRESS.value
        )

        # Check the FAILED call
        self.assertEqual(
            calls[1][2]["data"]["attributes"]["status"], Status.FAILED.value
        )
        self.assertEqual(calls[1][2]["data"]["attributes"]["message"], "Test exception")

    @patch("gcp_shared.reporter.dd_request")
    def test_is_valid_workflow_id_404(self, mock_dd_request):
        """Test is_valid_workflow_id when workflow doesn't exist (404)."""
        mock_dd_request.return_value = ('{"error": "not found"}', 404)

        result = self.workflow_reporter.is_valid_workflow_id("final_step")

        self.assertTrue(result)
        mock_dd_request.assert_called_once_with(
            "GET",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup/test_workflow_id",
        )

    @patch("gcp_shared.reporter.dd_request")
    def test_is_valid_workflow_id_with_failed_steps(self, mock_dd_request):
        """Test is_valid_workflow_id when workflow has failed steps."""
        mock_dd_request.return_value = (
            '{"data": {"attributes": {"statuses": [{"status": "failed"}, {"status": "finished"}]}}}',
            200,
        )

        result = self.workflow_reporter.is_valid_workflow_id("final_step")

        self.assertFalse(result)
        mock_dd_request.assert_called_once_with(
            "GET",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup/test_workflow_id",
        )

    @patch("gcp_shared.reporter.dd_request")
    def test_is_valid_workflow_id_workflow_completed(self, mock_dd_request):
        """Test is_valid_workflow_id when workflow has completed successfully."""
        mock_dd_request.return_value = (
            '{"data": {"attributes": {"statuses": [{"step": "final_step", "status": "finished"}]}}}',
            200,
        )

        result = self.workflow_reporter.is_valid_workflow_id("final_step")

        self.assertFalse(result)
        mock_dd_request.assert_called_once_with(
            "GET",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup/test_workflow_id",
        )

    @patch("gcp_shared.reporter.dd_request")
    def test_is_valid_workflow_id_workflow_in_progress(self, mock_dd_request):
        """Test is_valid_workflow_id when workflow is still in progress."""
        mock_dd_request.return_value = (
            '{"data": {"attributes": {"statuses": [{"step": "scopes", "status": "finished"}, {"step": "selections", "status": "in_progress"}]}}}',
            200,
        )

        result = self.workflow_reporter.is_valid_workflow_id("final_step")

        self.assertTrue(result)
        mock_dd_request.assert_called_once_with(
            "GET",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup/test_workflow_id",
        )

    @patch("gcp_shared.reporter.dd_request")
    def test_is_valid_workflow_id_api_error(self, mock_dd_request):
        """Test is_valid_workflow_id when API returns error status."""
        mock_dd_request.return_value = ('{"error": "server error"}', 500)

        result = self.workflow_reporter.is_valid_workflow_id("final_step")

        self.assertFalse(result)
        mock_dd_request.assert_called_once_with(
            "GET",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup/test_workflow_id",
        )

    @patch("gcp_shared.reporter.dd_request")
    @patch("gcp_shared.reporter.gcloud")
    def test_handle_login_step_success(self, mock_gcloud, mock_dd_request):
        """Test handle_login_step when user is logged in."""
        mock_gcloud.return_value = [{"token": "dummy-token"}]
        mock_dd_request.return_value = ('{"status": "ok"}', 201)

        self.workflow_reporter.handle_login_step()

        actual_commands = [str(call[0][0]) for call in mock_gcloud.call_args_list]
        self.assertEqual(len(actual_commands), 1)
        self.assertEqual(actual_commands[0], "auth print-access-token")

    @patch("gcp_shared.reporter.dd_request")
    @patch("gcp_shared.reporter.gcloud")
    def test_handle_login_step_failure(self, mock_gcloud, mock_dd_request):
        """Test handle_login_step when user is not logged in."""
        mock_gcloud.return_value = []
        mock_dd_request.return_value = ('{"status": "ok"}', 201)

        with self.assertRaises(SystemExit) as context:
            self.workflow_reporter.handle_login_step()

        self.assertEqual(context.exception.code, 1)

    @patch("gcp_shared.reporter.gcloud")
    def test_handle_login_step_gcloud_not_found(self, mock_gcloud):
        """Test handle_login_step when gcloud command is not found."""
        mock_gcloud.side_effect = Exception("gcloud: command not found")

        with self.assertRaises(SystemExit) as context:
            self.workflow_reporter.handle_login_step()

        self.assertEqual(context.exception.code, 1)

    @patch("gcp_shared.reporter.dd_request")
    def test_is_scopes_step_already_completed_success(self, mock_dd_request):
        """Test is_scopes_step_already_completed when scopes step is finished."""
        mock_dd_request.return_value = (
            '{"data": {"attributes": {"statuses": [{"step": "scopes", "status": "finished"}]}}}',
            200,
        )

        result = self.workflow_reporter.is_scopes_step_already_completed()

        self.assertTrue(result)
        mock_dd_request.assert_called_once_with(
            "GET",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup/test_workflow_id",
        )

    @patch("gcp_shared.reporter.dd_request")
    def test_is_scopes_step_already_completed_not_finished(self, mock_dd_request):
        """Test is_scopes_step_already_completed when scopes step is not finished."""
        mock_dd_request.return_value = (
            '{"data": {"attributes": {"statuses": [{"step": "scopes", "status": "in_progress"}]}}}',
            200,
        )

        result = self.workflow_reporter.is_scopes_step_already_completed()

        self.assertFalse(result)
        mock_dd_request.assert_called_once_with(
            "GET",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup/test_workflow_id",
        )

    @patch("gcp_shared.reporter.dd_request")
    def test_is_scopes_step_already_completed_no_scopes_step(self, mock_dd_request):
        """Test is_scopes_step_already_completed when no scopes step exists."""
        mock_dd_request.return_value = (
            '{"data": {"attributes": {"statuses": [{"step": "other_step", "status": "finished"}]}}}',
            200,
        )

        result = self.workflow_reporter.is_scopes_step_already_completed()

        self.assertFalse(result)
        mock_dd_request.assert_called_once_with(
            "GET",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup/test_workflow_id",
        )

    @patch("gcp_shared.reporter.dd_request")
    def test_is_scopes_step_already_completed_http_error(self, mock_dd_request):
        """Test is_scopes_step_already_completed when HTTP request fails."""
        mock_dd_request.return_value = ('{"error": "not found"}', 404)

        result = self.workflow_reporter.is_scopes_step_already_completed()

        self.assertFalse(result)
        mock_dd_request.assert_called_once_with(
            "GET",
            "/api/unstable/integration/gcp/workflow/gcp-integration-setup/test_workflow_id",
        )


if __name__ == "__main__":
    unittest.main()
