# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import unittest

from gcp_integration_quickstart.reporter import Status, WorkflowReporter


class TestWorkflowReporter(unittest.TestCase):
    """Test the WorkflowReporter class."""

    def setUp(self):
        def mock_dd_request(*args, **kwargs):
            return ('{"status": "ok"}', 201)

        self.mock_dd_request = mock_dd_request
        self.workflow_reporter = WorkflowReporter(
            "test_workflow_id", self.mock_dd_request
        )

    def test_report(self):
        metadata = {"key": "value"}
        message = "Test message"

        def mock_dd_request(method, path, body):
            return ('{"status": "ok"}', 201)

        workflow_reporter = WorkflowReporter("test_workflow_id", mock_dd_request)

        # Should not raise an exception
        workflow_reporter.report(
            "test_step", Status.IN_PROGRESS, metadata=metadata, message=message
        )

    def test_report_failure(self):
        def mock_dd_request(method, path, body):
            return ('{"error": "bad request"}', 400)

        workflow_reporter = WorkflowReporter("test_workflow_id", mock_dd_request)

        with self.assertRaises(RuntimeError) as ctx:
            workflow_reporter.report("test_step", Status.IN_PROGRESS)

        self.assertEqual(
            str(ctx.exception), 'failed to report status: {"error": "bad request"}'
        )

    def test_report_step_context_manager_success(self):
        """Test the report_step context manager on success."""
        call_count = 0
        calls = []

        def mock_dd_request(method, path, body):
            nonlocal call_count
            call_count += 1
            calls.append((method, path, body))
            return ('{"status": "ok"}', 201)

        workflow_reporter = WorkflowReporter("test_workflow_id", mock_dd_request)

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

    def test_report_step_context_manager_exception(self):
        """Test the report_step context manager on exception."""
        call_count = 0
        calls = []

        def mock_dd_request(method, path, body):
            nonlocal call_count
            call_count += 1
            calls.append((method, path, body))
            return ('{"status": "ok"}', 201)

        workflow_reporter = WorkflowReporter("test_workflow_id", mock_dd_request)

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


if __name__ == "__main__":
    unittest.main()
