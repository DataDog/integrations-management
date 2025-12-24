# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import os
import unittest
from unittest.mock import patch

from gcp_agentless_setup.config import Config, parse_config
from gcp_agentless_setup.errors import ConfigurationError


class TestConfig(unittest.TestCase):
    """Test the Config class."""

    def test_all_projects_deduplicates_scanner_project(self):
        """Scanner project should be included only once even if in projects_to_scan."""
        config = Config(
            api_key="key",
            app_key="app",
            site="datadoghq.com",
            scanner_project="scanner-proj",
            region="us-central1",
            projects_to_scan=["scanner-proj", "other-proj"],
        )

        self.assertEqual(sorted(config.all_projects), ["other-proj", "scanner-proj"])

    def test_all_projects_adds_scanner_project(self):
        """Scanner project should be added if not in projects_to_scan."""
        config = Config(
            api_key="key",
            app_key="app",
            site="datadoghq.com",
            scanner_project="scanner-proj",
            region="us-central1",
            projects_to_scan=["proj-a", "proj-b"],
        )

        self.assertEqual(
            sorted(config.all_projects), ["proj-a", "proj-b", "scanner-proj"]
        )

    def test_other_projects_excludes_scanner(self):
        """other_projects should exclude the scanner project."""
        config = Config(
            api_key="key",
            app_key="app",
            site="datadoghq.com",
            scanner_project="scanner-proj",
            region="us-central1",
            projects_to_scan=["scanner-proj", "proj-a", "proj-b"],
        )

        self.assertEqual(config.other_projects, ["proj-a", "proj-b"])

    def test_other_projects_empty_when_only_scanner(self):
        """other_projects should be empty when only scanner is scanned."""
        config = Config(
            api_key="key",
            app_key="app",
            site="datadoghq.com",
            scanner_project="scanner-proj",
            region="us-central1",
            projects_to_scan=["scanner-proj"],
        )

        self.assertEqual(config.other_projects, [])


class TestParseConfig(unittest.TestCase):
    """Test the parse_config function."""

    @patch.dict(
        os.environ,
        {
            "DD_API_KEY": "test-api-key",
            "DD_APP_KEY": "test-app-key",
            "DD_SITE": "datadoghq.com",
            "GCP_SCANNER_PROJECT": "my-scanner",
            "GCP_REGION": "us-central1",
            "GCP_PROJECTS_TO_SCAN": "proj-a, proj-b, proj-c",
        },
        clear=True,
    )
    def test_parse_config_success(self):
        """Test successful config parsing."""
        config = parse_config()

        self.assertEqual(config.api_key, "test-api-key")
        self.assertEqual(config.app_key, "test-app-key")
        self.assertEqual(config.site, "datadoghq.com")
        self.assertEqual(config.scanner_project, "my-scanner")
        self.assertEqual(config.region, "us-central1")
        self.assertEqual(config.projects_to_scan, ["proj-a", "proj-b", "proj-c"])

    @patch.dict(
        os.environ,
        {
            "DD_API_KEY": "key",
            "DD_APP_KEY": "app",
            "DD_SITE": "datadoghq.com",
            "GCP_SCANNER_PROJECT": "scanner",
            "GCP_REGION": "us-central1",
            "GCP_PROJECTS_TO_SCAN": "  proj-a  ,  proj-b  ",
        },
        clear=True,
    )
    def test_parse_config_trims_whitespace(self):
        """Test that whitespace is trimmed from project names."""
        config = parse_config()

        self.assertEqual(config.projects_to_scan, ["proj-a", "proj-b"])

    @patch.dict(os.environ, {}, clear=True)
    def test_parse_config_missing_all_vars(self):
        """Test error when all required vars are missing."""
        with self.assertRaises(ConfigurationError) as ctx:
            parse_config()

        self.assertIn("DD_API_KEY", ctx.exception.detail)
        self.assertIn("DD_APP_KEY", ctx.exception.detail)
        self.assertIn("DD_SITE", ctx.exception.detail)

    @patch.dict(
        os.environ,
        {
            "DD_API_KEY": "key",
            "DD_APP_KEY": "app",
            "DD_SITE": "datadoghq.com",
            "GCP_SCANNER_PROJECT": "scanner",
            "GCP_REGION": "us-central1",
            "GCP_PROJECTS_TO_SCAN": "  ,  ,  ",
        },
        clear=True,
    )
    def test_parse_config_empty_projects_list(self):
        """Test error when projects list contains only whitespace."""
        with self.assertRaises(ConfigurationError) as ctx:
            parse_config()

        self.assertIn("at least one project", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()

