# Unless explicitly stated otherwise all files in this repository are licensed under the Apache-2 License.
# This product includes software developed at Datadog (https://www.datadoghq.com/) Copyright 2025 Datadog, Inc.

import unittest

from gcp_agentless_setup.config import Config
from gcp_agentless_setup.terraform import (
    generate_terraform_config,
    generate_tfvars,
    MODULE_VERSION,
)


# Test fixture for api_key_secret_id
TEST_API_KEY_SECRET_ID = "projects/scanner-project/secrets/datadog-agentless-scanner-api-key"


class TestGenerateTerraformConfig(unittest.TestCase):
    """Test Terraform configuration generation."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = Config(
            api_key="test-api-key",
            app_key="test-app-key",
            site="datadoghq.com",
            scanner_project="scanner-project",
            regions=["us-central1"],
            projects_to_scan=["scanner-project", "other-project"],
        )

    def test_generates_backend_config(self):
        """Test that backend configuration is generated correctly."""
        tf = generate_terraform_config(self.config, "my-state-bucket", TEST_API_KEY_SECRET_ID)

        self.assertIn('bucket = "my-state-bucket"', tf)
        self.assertIn('prefix = "agentless-scanner"', tf)

    def test_generates_scanner_project_provider(self):
        """Test that scanner project provider is generated with region alias."""
        tf = generate_terraform_config(self.config, "bucket", TEST_API_KEY_SECRET_ID)

        self.assertIn('project = "scanner-project"', tf)
        self.assertIn('region  = "us-central1"', tf)
        self.assertIn('alias   = "us_central1"', tf)

    def test_generates_other_project_providers(self):
        """Test that providers for other projects are generated with aliases."""
        tf = generate_terraform_config(self.config, "bucket", TEST_API_KEY_SECRET_ID)

        # Other project should have aliased provider
        self.assertIn('alias   = "other_project"', tf)
        self.assertIn('project = "other-project"', tf)

    def test_generates_impersonated_sa_modules(self):
        """Test that impersonated SA modules are generated for other projects."""
        tf = generate_terraform_config(self.config, "bucket", TEST_API_KEY_SECRET_ID)

        # Should have module for other project
        self.assertIn('module "agentless_impersonated_sa_other_project"', tf)
        self.assertIn("google = google.other_project", tf)

    def test_generates_scan_options_for_all_projects(self):
        """Test that scan options are generated for all projects."""
        tf = generate_terraform_config(self.config, "bucket", TEST_API_KEY_SECRET_ID)

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

    def test_no_extra_project_providers_when_only_scanner(self):
        """Test no aliased providers for other projects when only scanning scanner project."""
        config = Config(
            api_key="key",
            app_key="app",
            site="datadoghq.com",
            scanner_project="only-project",
            regions=["us-central1"],
            projects_to_scan=["only-project"],
        )

        tf = generate_terraform_config(config, "bucket", TEST_API_KEY_SECRET_ID)

        # Should have region alias but not project alias
        self.assertIn('alias   = "us_central1"', tf)
        # Should not have impersonated SA modules
        self.assertNotIn("agentless_impersonated_sa_", tf)

    def test_generates_multiple_region_providers_and_modules(self):
        """Test that multiple regions generate multiple providers and scanner modules."""
        config = Config(
            api_key="key",
            app_key="app",
            site="datadoghq.com",
            scanner_project="scanner-project",
            regions=["us-central1", "europe-west1"],
            projects_to_scan=["scanner-project"],
        )

        tf = generate_terraform_config(config, "bucket", TEST_API_KEY_SECRET_ID)

        # Should have provider for each region
        self.assertIn('alias   = "us_central1"', tf)
        self.assertIn('alias   = "europe_west1"', tf)
        self.assertIn('region  = "us-central1"', tf)
        self.assertIn('region  = "europe-west1"', tf)

        # Should have scanner module for each region
        self.assertIn('module "datadog_agentless_scanner_us_central1"', tf)
        self.assertIn('module "datadog_agentless_scanner_europe_west1"', tf)

        # Should have unique VPC names
        self.assertIn('vpc_name          = "datadog-agentless-scanner-us-central1"', tf)
        self.assertIn('vpc_name          = "datadog-agentless-scanner-europe-west1"', tf)

    def test_uses_correct_module_version(self):
        """Test that the correct module version is used."""
        tf = generate_terraform_config(self.config, "bucket", TEST_API_KEY_SECRET_ID)

        self.assertIn(f"ref={MODULE_VERSION}", tf)

    def test_uses_api_key_secret_id_not_raw_key(self):
        """Test that api_key_secret_id is used instead of raw api_key."""
        tf = generate_terraform_config(self.config, "bucket", TEST_API_KEY_SECRET_ID)

        # Should use api_key_secret_id in module
        self.assertIn(f'api_key_secret_id = "{TEST_API_KEY_SECRET_ID}"', tf)

        # Should NOT have raw api_key variable
        self.assertNotIn('variable "datadog_api_key"', tf)

        # Should NOT have api_key in module
        self.assertNotIn("api_key  =", tf)


class TestGenerateTfvars(unittest.TestCase):
    """Test terraform.tfvars generation."""

    def test_generates_tfvars_with_credentials(self):
        """Test that tfvars contains app_key and site but not api_key."""
        config = Config(
            api_key="my-api-key",
            app_key="my-app-key",
            site="us5.datadoghq.com",
            scanner_project="proj",
            regions=["us-central1"],
            projects_to_scan=["proj"],
        )

        tfvars = generate_tfvars(config)

        # API key should NOT be in tfvars (stored in Secret Manager)
        self.assertNotIn("datadog_api_key", tfvars)
        self.assertNotIn("my-api-key", tfvars)

        # App key and site should still be present
        self.assertIn('datadog_app_key = "my-app-key"', tfvars)
        self.assertIn('datadog_site    = "us5.datadoghq.com"', tfvars)


if __name__ == "__main__":
    unittest.main()
