# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import unittest

from gcp_agentless_setup.config import Config
from gcp_agentless_setup.terraform import (
    generate_terraform_config,
    generate_tfvars,
    MODULE_VERSION,
)


class TestGenerateTerraformConfig(unittest.TestCase):
    """Test Terraform configuration generation."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = Config(
            api_key="test-api-key",
            app_key="test-app-key",
            site="datadoghq.com",
            scanner_project="scanner-project",
            region="us-central1",
            projects_to_scan=["scanner-project", "other-project"],
        )

    def test_generates_backend_config(self):
        """Test that backend configuration is generated correctly."""
        tf = generate_terraform_config(self.config, "my-state-bucket")

        self.assertIn('bucket = "my-state-bucket"', tf)
        self.assertIn('prefix = "agentless-scanner"', tf)

    def test_generates_scanner_project_provider(self):
        """Test that scanner project provider is generated."""
        tf = generate_terraform_config(self.config, "bucket")

        self.assertIn('project = "scanner-project"', tf)
        self.assertIn('region  = "us-central1"', tf)

    def test_generates_other_project_providers(self):
        """Test that providers for other projects are generated with aliases."""
        tf = generate_terraform_config(self.config, "bucket")

        # Other project should have aliased provider
        self.assertIn('alias   = "other_project"', tf)
        self.assertIn('project = "other-project"', tf)

    def test_generates_impersonated_sa_modules(self):
        """Test that impersonated SA modules are generated for other projects."""
        tf = generate_terraform_config(self.config, "bucket")

        # Should have module for other project
        self.assertIn('module "agentless_impersonated_sa_other_project"', tf)
        self.assertIn("google = google.other_project", tf)

    def test_generates_scan_options_for_all_projects(self):
        """Test that scan options are generated for all projects."""
        tf = generate_terraform_config(self.config, "bucket")

        # Scanner project scan options
        self.assertIn(
            'resource "datadog_agentless_scanning_gcp_scan_options" "scanner_project"',
            tf,
        )
        self.assertIn('gcp_project_id     = "scanner-project"', tf)

        # Other project scan options
        self.assertIn(
            'resource "datadog_agentless_scanning_gcp_scan_options" "scan_other_project"',
            tf,
        )
        self.assertIn('gcp_project_id     = "other-project"', tf)

    def test_no_extra_providers_when_only_scanner(self):
        """Test no aliased providers when only scanning scanner project."""
        config = Config(
            api_key="key",
            app_key="app",
            site="datadoghq.com",
            scanner_project="only-project",
            region="us-central1",
            projects_to_scan=["only-project"],
        )

        tf = generate_terraform_config(config, "bucket")

        # Should not have any aliased providers
        self.assertNotIn("alias   =", tf)
        # Should not have impersonated SA modules
        self.assertNotIn("agentless_impersonated_sa_", tf)

    def test_uses_correct_module_version(self):
        """Test that the correct module version is used."""
        tf = generate_terraform_config(self.config, "bucket")

        self.assertIn(f"ref={MODULE_VERSION}", tf)


class TestGenerateTfvars(unittest.TestCase):
    """Test terraform.tfvars generation."""

    def test_generates_tfvars_with_credentials(self):
        """Test that tfvars contains all required variables."""
        config = Config(
            api_key="my-api-key",
            app_key="my-app-key",
            site="us5.datadoghq.com",
            scanner_project="proj",
            region="us-central1",
            projects_to_scan=["proj"],
        )

        tfvars = generate_tfvars(config)

        self.assertIn('datadog_api_key = "my-api-key"', tfvars)
        self.assertIn('datadog_app_key = "my-app-key"', tfvars)
        self.assertIn('datadog_site    = "us5.datadoghq.com"', tfvars)


if __name__ == "__main__":
    unittest.main()

