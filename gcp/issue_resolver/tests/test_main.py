# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import os
import unittest
from unittest.mock import patch

from gcp_issue_resolver.main import (
    LoggingStepReporter,
    _project_from_email,
    fix_permissions,
    main,
)

_VALID_EMAIL = "my-sa@my-project.iam.gserviceaccount.com"
_VALID_ENV = {"DD_API_KEY": "key", "DD_APP_KEY": "app", "DD_SITE": "datadoghq.com"}
_STS_RESPONSE = ('{"data": {"id": "dd-principal@datadog-prod.iam.gserviceaccount.com"}}', 200)


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


class TestProjectFromEmail(unittest.TestCase):
    def test_extracts_project_id(self):
        self.assertEqual(_project_from_email("sa@my-project.iam.gserviceaccount.com"), "my-project")

    def test_extracts_hyphenated_project_id(self):
        self.assertEqual(_project_from_email("my-sa@proj-123.iam.gserviceaccount.com"), "proj-123")


if __name__ == "__main__":
    unittest.main()
