# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.

# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import io
import os
import unittest
from unittest.mock import Mock, patch

from gcp_agentless_setup.errors import TerraformError
from gcp_integration_quickstart.agentless import (
    is_agentless_requested,
    prepare_agentless_setup,
    run_agentless_setup,
)

BASE_ENV = {
    "DD_API_KEY": "api-key",
    "DD_APP_KEY": "app-key",
    "DD_SITE": "datadoghq.com",
    "WORKFLOW_ID": "integration-workflow-id",
}

AGENTLESS_ENV = {
    "AGENTLESS_WORKFLOW_ID": "agentless-workflow-id",
    "SCANNER_PROJECT": "scanner-project",
    "SCANNER_REGIONS": "us-central1",
    "PROJECTS_TO_SCAN": "proj1,proj2",
}


class TestIsAgentlessRequested(unittest.TestCase):
    @patch.dict(os.environ, BASE_ENV, clear=True)
    def test_not_requested_without_agentless_vars(self):
        self.assertFalse(is_agentless_requested())

    @patch.dict(os.environ, {**BASE_ENV, "SCANNER_PROJECT": "  "}, clear=True)
    def test_blank_values_are_ignored(self):
        self.assertFalse(is_agentless_requested())

    @patch.dict(os.environ, {**BASE_ENV, "SCANNER_REGIONS": "us-central1"}, clear=True)
    def test_requested_with_any_agentless_var(self):
        self.assertTrue(is_agentless_requested())


class TestPrepareAgentlessSetup(unittest.TestCase):
    @patch("gcp_integration_quickstart.agentless.validate_credentials_and_workflow")
    @patch.dict(os.environ, {**BASE_ENV, **AGENTLESS_ENV}, clear=True)
    def test_uses_agentless_workflow_id(self, mock_validate):
        config, reporter = prepare_agentless_setup()

        self.assertEqual(config.workflow_id, "agentless-workflow-id")
        self.assertEqual(config.scanner_project, "scanner-project")
        self.assertEqual(config.projects_to_scan, ["proj1", "proj2"])
        self.assertEqual(reporter.workflow.workflow_id, "agentless-workflow-id")
        mock_validate.assert_called_once_with(config, reporter)

    @patch("gcp_integration_quickstart.agentless.validate_credentials_and_workflow")
    @patch.dict(os.environ, {**BASE_ENV, "SCANNER_PROJECT": "scanner-project"}, clear=True)
    def test_partial_config_exits_before_validation(self, mock_validate):
        with patch("sys.stdout", new_callable=io.StringIO) as stdout, self.assertRaises(SystemExit) as ctx:
            prepare_agentless_setup()

        self.assertEqual(ctx.exception.code, 1)
        mock_validate.assert_not_called()
        output = stdout.getvalue()
        self.assertIn("AGENTLESS_WORKFLOW_ID is required", output)
        self.assertIn("Agentless Scanning setup requires all of", output)
        self.assertNotIn("gcp_agentless_setup.pyz", output)

    @patch("gcp_integration_quickstart.agentless.validate_credentials_and_workflow")
    @patch.dict(
        os.environ,
        {**BASE_ENV, **AGENTLESS_ENV, "SCANNER_REGIONS": "r1,r2,r3,r4,r5"},
        clear=True,
    )
    def test_invalid_config_exits_without_partial_hint(self, mock_validate):
        with patch("sys.stdout", new_callable=io.StringIO) as stdout, self.assertRaises(SystemExit) as ctx:
            prepare_agentless_setup()

        self.assertEqual(ctx.exception.code, 1)
        mock_validate.assert_not_called()
        self.assertIn("cannot exceed 4 regions", stdout.getvalue())
        self.assertNotIn("requires all of", stdout.getvalue())


class TestRunAgentlessSetup(unittest.TestCase):
    @patch("gcp_integration_quickstart.agentless.deploy")
    def test_success(self, mock_deploy):
        config, reporter = Mock(), Mock()

        run_agentless_setup(config, reporter)

        mock_deploy.assert_called_once_with(config, reporter)

    @patch("gcp_integration_quickstart.agentless.deploy")
    def test_failure_exits_non_zero(self, mock_deploy):
        for error in (TerraformError("terraform apply failed"), RuntimeError("boom")):
            mock_deploy.side_effect = error
            with self.subTest(error=error), self.assertRaises(SystemExit) as ctx:
                run_agentless_setup(Mock(), Mock())
            self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
