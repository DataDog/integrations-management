# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import os
import unittest
from contextlib import contextmanager
from unittest.mock import Mock, patch

from gcp_issue_resolver.main import (
    LoggingStepReporter,
    _project_from_email,
    fix_permissions,
    main,
)

_VALID_EMAIL = "my-sa@my-project.iam.gserviceaccount.com"
_VALID_ENV = {"DD_API_KEY": "key", "DD_APP_KEY": "app", "DD_SITE": "datadoghq.com"}
_UI_ENV = {
    **_VALID_ENV,
    "WORKFLOW_ID": "11111111-1111-1111-1111-111111111111",
    "ACCOUNT_EMAIL": _VALID_EMAIL,
}
_STS_RESPONSE = ('{"data": {"id": "dd-principal@datadog-prod.iam.gserviceaccount.com"}}', 200)


@contextmanager
def _step_ctx(step_reporter):
    yield step_reporter


class TestMain(unittest.TestCase):
    @patch("gcp_issue_resolver.main.gcloud")
    @patch("gcp_issue_resolver.main.dd_request")
    @patch("gcp_issue_resolver.main.ensure_service_account_permissions")
    def test_valid_email_and_project_applies_all_permissions(self, mock_ensure, mock_dd_request, mock_gcloud):
        mock_dd_request.return_value = _STS_RESPONSE

        with patch.dict(os.environ, _VALID_ENV, clear=True):
            with patch("sys.argv", ["gcp_issue_resolver", _VALID_EMAIL, "my-project"]):
                main()

        mock_ensure.assert_called_once()
        mock_dd_request.assert_called_once()
        mock_gcloud.assert_called_once()

    def test_invalid_email_raises_value_error_before_any_gcp_call(self):
        with patch.dict(os.environ, _VALID_ENV, clear=True):
            with patch("sys.argv", ["gcp_issue_resolver", "not-a-valid-email", "my-project"]):
                with self.assertRaises(ValueError) as ctx:
                    main()

        self.assertIn("Invalid service account email", str(ctx.exception))

    def test_missing_env_vars_exits_before_any_api_call(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("sys.argv", ["gcp_issue_resolver", _VALID_EMAIL, "my-project"]):
                with self.assertRaises(SystemExit):
                    main()

    def test_too_few_args_exits(self):
        with patch.dict(os.environ, _VALID_ENV, clear=True):
            with patch("sys.argv", ["gcp_issue_resolver"]):
                with self.assertRaises(SystemExit):
                    main()


class TestFixPermissions(unittest.TestCase):
    @patch("gcp_issue_resolver.main.gcloud")
    @patch("gcp_issue_resolver.main.dd_request")
    @patch("gcp_issue_resolver.main.ensure_service_account_permissions")
    def test_calls_ensure_permissions_for_each_project(self, mock_ensure, mock_dd_request, _mock_gcloud):
        mock_dd_request.return_value = _STS_RESPONSE
        reporter = LoggingStepReporter()

        fix_permissions(reporter, _VALID_EMAIL, ["proj-a", "proj-b"])

        self.assertEqual(mock_ensure.call_count, 2)
        projects_called = [c[0][1] for c in mock_ensure.call_args_list]
        self.assertEqual(projects_called, ["proj-a", "proj-b"])

    @patch("gcp_issue_resolver.main.gcloud")
    @patch("gcp_issue_resolver.main.dd_request")
    @patch("gcp_issue_resolver.main.ensure_service_account_permissions")
    def test_delegate_permission_applied_once_regardless_of_project_count(
        self, _mock_ensure, mock_dd_request, _mock_gcloud
    ):
        mock_dd_request.return_value = _STS_RESPONSE
        reporter = LoggingStepReporter()

        fix_permissions(reporter, _VALID_EMAIL, ["proj-a", "proj-b", "proj-c"])

        mock_dd_request.assert_called_once()

    @patch("gcp_issue_resolver.main.ensure_service_account_permissions")
    def test_sa_not_found_propagates_runtime_error(self, mock_ensure):
        mock_ensure.side_effect = RuntimeError("Service account 'sa@proj.iam.gserviceaccount.com' not found in project 'proj'")
        reporter = LoggingStepReporter()

        with self.assertRaises(RuntimeError) as ctx:
            fix_permissions(reporter, _VALID_EMAIL, ["my-project"])

        self.assertIn("not found", str(ctx.exception))

    @patch("gcp_issue_resolver.main.gcloud")
    @patch("gcp_issue_resolver.main.dd_request")
    @patch("gcp_issue_resolver.main.ensure_service_account_permissions")
    def test_delegate_binding_uses_project_from_email(self, _mock_ensure, mock_dd_request, mock_gcloud):
        mock_dd_request.return_value = _STS_RESPONSE
        reporter = LoggingStepReporter()

        fix_permissions(reporter, _VALID_EMAIL, ["other-project"])

        gcloud_cmd = str(mock_gcloud.call_args[0][0])
        self.assertIn("my-project", gcloud_cmd)


class TestMainUiMode(unittest.TestCase):
    def _make_workflow_reporter(self, mock_cls, user_selections):
        step_reporter = Mock()
        workflow_reporter = Mock()
        workflow_reporter.is_valid_workflow_id.return_value = True
        workflow_reporter.receive_user_selections.return_value = user_selections
        workflow_reporter.report_step.side_effect = lambda *_a, **_k: _step_ctx(step_reporter)
        mock_cls.return_value = workflow_reporter
        return workflow_reporter, step_reporter

    @patch("gcp_issue_resolver.main.gcloud")
    @patch("gcp_issue_resolver.main.dd_request")
    @patch("gcp_issue_resolver.main.ensure_service_account_permissions")
    @patch("gcp_issue_resolver.main.WorkflowReporter")
    def test_ui_mode_waits_for_project_selection_and_fixes_permissions(
        self, mock_workflow_reporter_cls, mock_ensure, mock_dd_request, _mock_gcloud
    ):
        mock_dd_request.return_value = _STS_RESPONSE
        workflow_reporter, _step_reporter = self._make_workflow_reporter(
            mock_workflow_reporter_cls,
            {"project_ids": ["proj-a", "proj-b"]},
        )

        with patch.dict(os.environ, _UI_ENV, clear=True):
            with patch("sys.argv", ["gcp_issue_resolver"]):
                main()

        workflow_reporter.handle_login_step.assert_called_once()
        self.assertEqual(mock_ensure.call_count, 2)
        mock_dd_request.assert_called_once()

    @patch("gcp_issue_resolver.main.WorkflowReporter")
    def test_ui_mode_rejects_non_string_project_ids(self, mock_workflow_reporter_cls):
        workflow_reporter, _step_reporter = self._make_workflow_reporter(
            mock_workflow_reporter_cls,
            {"project_ids": [{"id": "proj-a"}]},
        )

        with patch.dict(os.environ, _UI_ENV, clear=True):
            with patch("sys.argv", ["gcp_issue_resolver"]):
                with self.assertRaises(SystemExit) as ctx:
                    main()

        self.assertEqual(ctx.exception.code, 1)
        workflow_reporter.report_step.assert_called_once()

    @patch("gcp_issue_resolver.main.WorkflowReporter")
    def test_ui_mode_rejects_empty_project_ids(self, mock_workflow_reporter_cls):
        self._make_workflow_reporter(mock_workflow_reporter_cls, {"project_ids": []})

        with patch.dict(os.environ, _UI_ENV, clear=True):
            with patch("sys.argv", ["gcp_issue_resolver"]):
                with self.assertRaises(SystemExit) as ctx:
                    main()

        self.assertEqual(ctx.exception.code, 1)

    @patch("gcp_issue_resolver.main.ensure_service_account_permissions")
    @patch("gcp_shared.reporter.gcloud", return_value="token")
    @patch("gcp_shared.reporter.dd_request")
    def test_ui_mode_reports_iam_permission_failure_to_ui(
        self, mock_dd_request, _mock_gcloud, mock_ensure
    ):
        get_calls = {"count": 0}

        def dd_side_effect(method, path, body=None):
            if method == "GET":
                get_calls["count"] += 1
                if get_calls["count"] == 1:
                    return ("", 404)
                return (
                    '{"data": {"attributes": {"metadata": {"selections": {"project_ids": ["proj-a"]}}}}}',
                    200,
                )
            return ("{}", 201)

        mock_dd_request.side_effect = dd_side_effect
        mock_ensure.side_effect = RuntimeError(
            "Your account (user@example.com) does not have permission 'iam.serviceAccounts.list' "
            "on project 'proj-a'. Ask your GCP administrator to grant you the IAM permissions "
            "needed to repair this integration."
        )

        with patch.dict(os.environ, _UI_ENV, clear=True):
            with patch("sys.argv", ["gcp_issue_resolver"]):
                with self.assertRaises(SystemExit) as ctx:
                    main()

        self.assertEqual(ctx.exception.code, 1)

        failed_reports = [
            call
            for call in mock_dd_request.call_args_list
            if call[0][0] == "POST"
            and call[0][2]["data"]["attributes"]["status"] == "failed"
        ]
        self.assertEqual(len(failed_reports), 1)
        self.assertIn(
            "iam.serviceAccounts.list",
            failed_reports[0][0][2]["data"]["attributes"]["message"],
        )

    def test_ui_mode_rejects_invalid_email_env_var(self):
        env = {**_UI_ENV, "ACCOUNT_EMAIL": "not-a-valid-email"}

        with patch.dict(os.environ, env, clear=True):
            with patch("sys.argv", ["gcp_issue_resolver"]):
                with self.assertRaises(ValueError) as ctx:
                    main()

        self.assertIn("Invalid service account email", str(ctx.exception))

    def test_ui_mode_exits_when_email_env_var_missing(self):
        env = {k: v for k, v in _UI_ENV.items() if k != "ACCOUNT_EMAIL"}

        with patch.dict(os.environ, env, clear=True):
            with patch("sys.argv", ["gcp_issue_resolver"]):
                with self.assertRaises(SystemExit):
                    main()

    @patch("gcp_issue_resolver.main.WorkflowReporter")
    def test_ui_mode_exits_when_workflow_already_used(self, mock_workflow_reporter_cls):
        workflow_reporter = Mock()
        workflow_reporter.is_valid_workflow_id.return_value = False
        mock_workflow_reporter_cls.return_value = workflow_reporter

        with patch.dict(os.environ, _UI_ENV, clear=True):
            with patch("sys.argv", ["gcp_issue_resolver"]):
                with self.assertRaises(SystemExit):
                    main()

        workflow_reporter.handle_login_step.assert_not_called()


class TestProjectFromEmail(unittest.TestCase):
    def test_extracts_project_id(self):
        self.assertEqual(_project_from_email("sa@my-project.iam.gserviceaccount.com"), "my-project")

    def test_extracts_hyphenated_project_id(self):
        self.assertEqual(_project_from_email("my-sa@proj-123.iam.gserviceaccount.com"), "proj-123")


if __name__ == "__main__":
    unittest.main()
